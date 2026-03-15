import os
import sys
import platform
import logging

import yfinance as yf
from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv("stack.env", override=True)


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] - [%(levelname)s] - %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S",
    stream=sys.stdout,
)


if platform.system().lower() == "linux":
    # Define a writable location for yfinance timezone cache
    cache_dir = "/tmp/yfinance_cache"
    os.makedirs(cache_dir, exist_ok=True)

    # Point yfinance to that directory
    yf.set_tz_cache_location(cache_dir)
