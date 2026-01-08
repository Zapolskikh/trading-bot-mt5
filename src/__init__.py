import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load env variables
load_dotenv(".env")
load_dotenv("stack.env", override=True)
