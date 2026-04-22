import math
import logging

logger = logging.getLogger(__name__)


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

    def _get_client(self):
        from ..config import Config
        if not Config.OPENAI_API_KEY:
            return None
        from openai import OpenAI
        return OpenAI(api_key=Config.OPENAI_API_KEY)

    def _embed(self, texts):
        client = self._get_client()
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

        embeddings = self._embed(chunks)
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
        client = self._get_client()
        if not client:
            return None

        try:
            with self.app.app_context():
                from ..models import KnowledgeDocument
                docs = KnowledgeDocument.query.filter_by(group_id=group_id).all()
                all_chunks = []
                for doc in docs:
                    for ch in (doc.chunks or []):
                        if ch.get("embedding"):
                            all_chunks.append(ch)

            if not all_chunks:
                return None

            q_resp = client.embeddings.create(model="text-embedding-3-small", input=question)
            q_emb = q_resp.data[0].embedding

            scored = sorted(
                all_chunks,
                key=lambda c: _cosine_similarity(q_emb, c["embedding"]),
                reverse=True,
            )
            context = "\n\n---\n\n".join(c["text"] for c in scored[:3])

            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Answer based only on the provided context. Be concise. If the answer is not in the context, say 'I don't have information about that in my knowledge base.'"},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
                ],
                max_tokens=350,
            )
            return resp.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"KB Q&A error: {e}")
            return None
