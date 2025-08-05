from typing import List, TypedDict
import os
import dotenv
import logging
from langchain.chat_models import init_chat_model
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_genai._common import GoogleGenerativeAIError
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain import hub
from langchain_core.prompts import PromptTemplate

from src.rag import PROMPTS

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

if not os.environ.get("GOOGLE_API_KEY"):
  logger.warning("GOOGLE API KEY is not found")


llm = init_chat_model("gemini-2.5-flash", model_provider="google_genai")
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")


vector_store = InMemoryVectorStore(embeddings)
prompt = PromptTemplate.from_template(PROMPTS.RAG_PROMPT)

class State(TypedDict):
    question: str
    context: List[Document]
    answer: str


def PDFLoader(file_path):
    loader = PyPDFLoader(
            file_path,
            mode='page'
        )

    docs = loader.load()
    return docs

def SplittingDocuments(docs):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,
    )
    
    all_splits = text_splitter.split_documents(docs)

    return all_splits

def StoringDocuments(splitted_docs):
    try:
        document_ids = vector_store.from_documents(splitted_docs)
    except GoogleGenerativeAIError as e:
        raise MemoryError(e)
    return document_ids

def Retrieve(state: State):
    retrieved_docs = vector_store.similarity_search(state["question"])
    return {"context": retrieved_docs}


def Generate(state: State):
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    messages = prompt.invoke({"question": state["question"], "context": docs_content})
    response = llm.invoke(messages)
    return {"answer": response.content}