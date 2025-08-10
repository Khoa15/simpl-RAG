import os
import dotenv
dotenv.load_dotenv()



print(os.environ.get("USE_MOCK_EMBEDDINGS"))

USE_MOCK_EMBEDDINGS = os.environ.get("USE_MOCK_EMBEDDINGS", "False").lower() in ("true", "1", "t")


print(USE_MOCK_EMBEDDINGS == True)