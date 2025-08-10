import io
import time
from typing import Any, List, TypedDict
import os
import dotenv
import logging

# Import các thư viện cần thiết, bao gồm InMemoryVectorStore
from langchain.chat_models import init_chat_model
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_community.vectorstores import InMemoryVectorStore
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.vectorstores import VectorStoreRetriever
from pypdf import PdfReader
from src.rag import PROMPTS

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

if not os.environ.get("GOOGLE_API_KEY"):
    logger.warning("GOOGLE API KEY is not found")

# Khởi tạo đối tượng embeddings một lần duy nhất
USE_MOCK_EMBEDDINGS = os.environ.get("USE_MOCK_EMBEDDINGS", "False").lower() in ("true", "1", "t")

# Định nghĩa một lớp mock để thay thế GoogleGenerativeAIEmbeddings
class MockEmbeddings:
    """Lớp giả lập cho GoogleGenerativeAIEmbeddings để tránh gọi API thật."""

    def __init__(self, **kwargs: Any):
        logger.info("Sử dụng MockEmbeddings. Các lệnh gọi API embeddings sẽ bị bỏ qua.")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Trả về một danh sách các vector giả lập."""
        # Trả về một vector giả lập có 768 chiều (chiều mặc định của gemini-embedding-001)
        time.sleep(1)
        return [[float(i) for i in range(768)] for _ in texts]
        
    def embed_query(self, text: str) -> List[float]:
        """Trả về một vector truy vấn giả lập."""
        time.sleep(1)
        return [float(i) for i in range(768)]

if USE_MOCK_EMBEDDINGS:
    embeddings = MockEmbeddings()
else:
    if not os.environ.get("GOOGLE_API_KEY"):
        logger.warning("GOOGLE API KEY is not found")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")


    
class State(TypedDict):
    question: str
    context: List[Document]
    answer: str

def PDFLoader(file_content: bytes):
    pdf_file_in_memory = io.BytesIO(file_content)
    reader = PdfReader(pdf_file_in_memory)
    pages = [page.extract_text() for page in reader.pages]
    
    # We return a list of langchain Document objects
    return [Document(page_content=text) for text in pages]
    # loader = PyPDFLoader(
    #     pdf_file_in_memory,
    #     mode='page'
    # )

    # docs = loader.load()
    # return docs

def SplittingDocuments(docs):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
    )
    
    all_splits = text_splitter.split_documents(docs)

    logger.warning(all_splits)
    return all_splits

def StoringDocuments(splitted_docs):
    """
    Tạo một vector store trong bộ nhớ và lưu dữ liệu.
    Hàm này không cần nhận embeddings nữa vì nó đã là global.
    """
    # Tạo vector store trong bộ nhớ
    vector_store = InMemoryVectorStore.from_documents(
        documents=splitted_docs,
        embedding=embeddings,
    )

    return vector_store

def RetrieveDocument(query: str, vector_store: InMemoryVectorStore):
    """
    Truy vấn thông tin từ vector store trong bộ nhớ.
    """
    retriever = vector_store.as_retriever()
    
    # Khởi tạo llm và prompt
    llm = init_chat_model("gemini-2.5-flash", model_provider="google_genai")
    prompt = PromptTemplate.from_template(PROMPTS.RAG_PROMPT)
    
    qa_chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return qa_chain.invoke(query)

class QuotaRateLimit(Exception):
    def __init__(self, *args):
        super().__init__(*args)
