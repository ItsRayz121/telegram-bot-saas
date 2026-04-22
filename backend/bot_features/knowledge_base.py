import math
import logging

logger = logging.getLogger(__name__)

PROVIDER_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    "custom": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "gemini": "gemini-1.5-flash",
}

PROVIDER_DEFAULT_BASE_URLS = {
    "openai": None,
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}


def _cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _chunk_text(text, chunk_size=400, overlap=50):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + chunk_size]))
        i += chunk_size - overlap
    return [c for c in chunks if c.strip()]


def _extract_text(content_bytes, file_type):
    try:
        if file_type in ("txt", "md"):
            return content_bytes.decode("utf-8", errors="ignore")
        elif file_type == "pdf":
            import PyPDF2, io
            reader = PyPDF2.PdfReader(io.BytesIO(content_bytes))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        elif file_type == "docx":
            import docx, io
            doc = docx.Document(io.BytesIO(content_bytes))
            return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        logger.error(f"Text extraction error ({file_type}): {e}")
    return ""


class KnowledgeBaseSystem:

    def __init__(self, app):
        self.app = app

    def _load_group_api_key(self, group_id):
        """Load and decrypt the group's custom API key config. Returns dict or None."""
        try:
            with self.app.app_context():
                from ..models import UserApiKey
                from ..utils.encryption import decrypt_value
                record = UserApiKey.query.filter_by(group_id=group_id, is_active=True).order_by(
                    UserApiKey.updated_at.desc()
                ).first()
                if not record:
                    return None
                return {
                    "provider": record.provider,
                    "api_key": decrypt_value(record.api_key_encrypted),
                    "base_url": record.base_url,
                    "model_name": record.model_name,
                }
        except Exception as e:
            logger.error(f"Failed to load group API key: {e}")
            return None

    def _get_openai_client(self, api_key=None, base_url=None):
        """Return an OpenAI-compatible client."""
        from openai import OpenAI
        from ..config import Config
        key = api_key or Config.OPENAI_API_KEY
        if not key:
            return None
        kwargs = {"api_key": key}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)

    def _embed(self, texts, group_id=None):
        """Embed texts using group's custom key if available, else env key."""
        key_config = self._load_group_api_key(group_id) if group_id else None

        if key_config and key_config["provider"] in ("openai", "openrouter", "custom"):
            client = self._get_openai_client(
                api_key=key_config["api_key"],
                base_url=key_config.get("base_url") or PROVIDER_DEFAULT_BASE_URLS.get(key_config["provider"]),
            )
        else:
            client = self._get_openai_client()

        if not client:
            return [None] * len(texts)

        try:
            results = []
            for i in range(0, len(texts), 100):
                batch = texts[i:i + 100]
                resp = client.embeddings.create(model="text-embedding-3-small", input=batch)
                results.extend(e.embedding for e in resp.data)
            return results
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return [None] * len(texts)

    def process_document(self, group_id, filename, file_type, content_bytes):
        text = _extract_text(content_bytes, file_type)
        if not text.strip():
            return None, "Could not extract text from file"

        chunks = _chunk_text(text)
        if not chunks:
            return None, "File appears to be empty"

        embeddings = self._embed(chunks, group_id=group_id)
        chunk_data = [
            {"text": c, "embedding": e}
            for c, e in zip(chunks, embeddings)
        ]

        with self.app.app_context():
            from ..models import KnowledgeDocument, db
            doc = KnowledgeDocument(
                group_id=group_id,
                filename=filename,
                file_type=file_type,
                content_text=text[:10000],
                chunks=chunk_data,
            )
            db.session.add(doc)
            db.session.commit()
            return doc.to_dict(), None

    async def answer_question(self, question, group_id):
        """Returns (answer: str|None, confidence: float)."""
        try:
            key_config = self._load_group_api_key(group_id)
            provider = key_config["provider"] if key_config else "openai"

            with self.app.app_context():
                from ..models import KnowledgeDocument
                docs = KnowledgeDocument.query.filter_by(group_id=group_id).all()
                all_chunks = []
                for doc in docs:
                    for ch in (doc.chunks or []):
                        if ch.get("embedding"):
                            all_chunks.append(ch)

            if not all_chunks:
                logger.debug(f"KB: No chunks found for group {group_id}")
                return None, 0.0

            # Embed question with appropriate client
            if key_config and provider in ("openai", "openrouter", "custom"):
                embed_client = self._get_openai_client(
                    api_key=key_config["api_key"],
                    base_url=key_config.get("base_url") or PROVIDER_DEFAULT_BASE_URLS.get(provider),
                )
            else:
                embed_client = self._get_openai_client()

            if not embed_client:
                logger.debug(f"KB: No embed client available for group {group_id}")
                return None, 0.0

            q_resp = embed_client.embeddings.create(model="text-embedding-3-small", input=question)
            q_emb = q_resp.data[0].embedding

            scored = sorted(
                all_chunks,
                key=lambda c: _cosine_similarity(q_emb, c["embedding"]),
                reverse=True,
            )
            top_score = _cosine_similarity(q_emb, scored[0]["embedding"]) if scored else 0.0
            logger.debug(f"KB: Top confidence score for group {group_id}: {top_score:.3f}")

            context = "\n\n---\n\n".join(c["text"] for c in scored[:3])

            answer = await self._generate_answer(question, context, key_config)
            return answer, top_score

        except Exception as e:
            logger.error(f"KB Q&A error: {e}")
            return None, 0.0

    async def _generate_answer(self, question, context, key_config):
        """Generate an answer from context using the appropriate provider."""
        provider = key_config["provider"] if key_config else "openai"

        system_prompt = (
            "You are a helpful assistant. Answer naturally and concisely based only on the provided context. "
            "If the answer is not in the context, say you don't have that information."
        )
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        if provider == "anthropic" and key_config:
            return await self._generate_anthropic(key_config, system_prompt, user_prompt)
        elif provider == "gemini" and key_config:
            return await self._generate_gemini(key_config, system_prompt, user_prompt)
        else:
            return await self._generate_openai_compatible(key_config, system_prompt, user_prompt, provider)

    async def _generate_openai_compatible(self, key_config, system_prompt, user_prompt, provider):
        from ..config import Config
        api_key = key_config["api_key"] if key_config else Config.OPENAI_API_KEY
        base_url = None
        model = "gpt-4o-mini"
        if key_config:
            base_url = key_config.get("base_url") or PROVIDER_DEFAULT_BASE_URLS.get(provider)
            model = key_config.get("model_name") or PROVIDER_DEFAULT_MODELS.get(provider, "gpt-4o-mini")

        client = self._get_openai_client(api_key=api_key, base_url=base_url)
        if not client:
            return None
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=400,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI-compatible generation error: {e}")
            return None

    async def _generate_anthropic(self, key_config, system_prompt, user_prompt):
        import requests as req
        model = key_config.get("model_name") or PROVIDER_DEFAULT_MODELS["anthropic"]
        base_url = key_config.get("base_url") or "https://api.anthropic.com"
        url = base_url.rstrip("/") + "/v1/messages"
        headers = {
            "x-api-key": key_config["api_key"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 400,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        try:
            resp = req.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("content", [{}])[0].get("text", "").strip()
        except Exception as e:
            logger.error(f"Anthropic generation error: {e}")
        return None

    async def _generate_gemini(self, key_config, system_prompt, user_prompt):
        import requests as req
        model = key_config.get("model_name") or PROVIDER_DEFAULT_MODELS["gemini"]
        api_key = key_config["api_key"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {"maxOutputTokens": 400},
        }
        try:
            resp = req.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("candidates", [{}])[0].get("content", {}).get(
                    "parts", [{}])[0].get("text", "").strip()
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
        return None
