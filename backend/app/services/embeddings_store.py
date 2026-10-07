import numpy as np


def embedding_to_bytes(vec: list[float]) -> bytes:
    arr = np.array(vec, dtype=np.float32)
    return arr.tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query / (np.linalg.norm(query) + 1e-10)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    m = matrix / norms
    return m @ q
