import os
import time

import pytest
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai.embeddings import OpenAIEmbeddings

from constants import VCR_HEADERS_EXCLUDE
from models.chroma_input_model import ChromaIntegration
from models.pinecone_input_model import EmbeddingsProvider, PineconeIntegration
from utils import add_item_checksum
from vector_stores.chroma import ChromaDatabase
from vector_stores.pinecone import PineconeDatabase

load_dotenv()
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

INDEX_NAME = "apify-unit-test"

d1 = Document(page_content="Expired->del", metadata={"item_id": "id1", "id": "id1#1", "checksum": "1", "last_seen_at": 0})
d2 = Document(page_content="Old->not-del", metadata={"item_id": "id2", "id": "id2#2", "checksum": "2", "last_seen_at": 1})
d3a = Document(page_content="Unchanged->upt-meta", metadata={"item_id": "id3", "id": "id3#3", "checksum": "3", "last_seen_at": 1})
d3b = Document(page_content="Unchanged->upt-meta", metadata={"item_id": "id3", "id": "id3#3", "checksum": "3", "last_seen_at": 2})
d4a = Document(page_content="Changed->del", metadata={"item_id": "id4", "id": "id4#4a", "checksum": "4", "last_seen_at": 1})
d4b = Document(page_content="Changed->del", metadata={"item_id": "id4", "id": "id4#4b", "checksum": "4", "last_seen_at": 1})
d4c = Document(page_content="Changed->add-new", metadata={"item_id": "id4", "id": "id4#4c", "checksum": "0", "last_seen_at": 2})
d5 = Document(page_content="New->add", metadata={"item_id": "id5", "id": "id5#5", "checksum": "5", "last_seen_at": 2})


@pytest.fixture(scope="function")
def crawl_1() -> list[Document]:
    return [d1, d2, d3a, d4a, d4b]


@pytest.fixture(scope="function")
def crawl_2() -> list[Document]:
    return [d3b, d4c, d5]


@pytest.fixture(scope="function")
def expected_results() -> list[Document]:
    return [d2, d3b, d4c, d5]


@pytest.fixture(scope="function")
def documents() -> list[Document]:
    d = Document(page_content="Content", metadata={"url": "https://url1.com"})
    return add_item_checksum([d], ["url"])


@pytest.mark.vcr(filter_headers=VCR_HEADERS_EXCLUDE)
@pytest.fixture(scope="function")
def db_pinecone(crawl_1) -> PineconeDatabase:
    db = PineconeDatabase(
        actor_input=PineconeIntegration(
            pineconeIndexName=INDEX_NAME,
            pineconeApiKey=os.getenv("PINECONE_API_KEY"),
            embeddingsProvider=EmbeddingsProvider.OpenAI,
            embeddingsApiKey=os.getenv("OPENAI_API_KEY"),
            datasetFields=["text"],
        ),
        embeddings=embeddings,
    )

    def delete_all():
        if r := list(db.index.list(prefix="id")):
            db.delete(ids=r)

    delete_all()
    # Insert initially crawled objects
    db.add_documents(documents=crawl_1, ids=[d.metadata["id"] for d in crawl_1])
    # Data freshness -  Pinecone is eventually consistent, so there can be a slight delay before new or changed records are visible to queries.
    time.sleep(5)

    yield db

    delete_all()


@pytest.mark.vcr(filter_headers=VCR_HEADERS_EXCLUDE)
@pytest.fixture(scope="function")
def db_chroma(crawl_1) -> ChromaDatabase:
    db = ChromaDatabase(
        actor_input=ChromaIntegration(
            chromaClientHost="localhost",
            embeddingsProvider=EmbeddingsProvider.OpenAI.value,
            embeddingsApiKey=os.getenv("OPENAI_API_KEY"),
            datasetFields=["text"],
            chromaCollectionName=INDEX_NAME,
        ),
        embeddings=embeddings,
    )

    def delete_all():
        r = db.index.get()
        if r["ids"]:
            db.delete(ids=r["ids"])

    delete_all()
    # Insert initially crawled objects
    db.add_documents(documents=crawl_1, ids=[d.metadata["id"] for d in crawl_1])

    yield db
    delete_all()
