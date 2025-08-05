import logging
from typing import Annotated, Union
from fastapi import FastAPI, Form, UploadFile
from fastapi.datastructures import FormData
from fastapi.middleware.cors import CORSMiddleware
from src.rag.preprocess import Generate, PDFLoader, SplittingDocuments, State, StoringDocuments, Retrieve
from langgraph.graph import START, StateGraph

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

graph_builder = StateGraph(State).add_sequence([Retrieve, Generate])
graph_builder.add_edge(START, "Retrieve")
graph = graph_builder.compile()

origins = [
    "http://localhost:3000", # frontend
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/api/v1/document")
async def get_document_from_client(file: UploadFile | None = None):
    if not file:
        return {
            'status': 200,
            "message": "No upload file sent"
            }
    
    import tempfile

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp.flush()


        docs = PDFLoader(tmp.name)

    splitted_docs = SplittingDocuments(docs)

    try:
        StoringDocuments(splitted_docs)
    except MemoryError as e:
        if e.args[0] == 500:
            return {
                'status': 500,
                'message': 'Your file is too large'
            }
        else:
            return {
                'status': 500,
                'message': 'Upload failed'
            }

    return {
        'status': 200,
        'message': 'Upload successfully'
    }

@app.post('/api/v1/retrieve')
async def retrieve_documents(query_text: Annotated[str, Form()]):
    result = graph.invoke({"question": query_text})
    
    return {
            'status': 200,
            'question': query_text,
            'message': result['answer']
        }
