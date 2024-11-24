import logging
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException
from urllib3.util.retry import Retry

from utils.sessions import SessionFactory

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def thirdparty_request(url, headers=None):
    """Handles all third-party requests / URL calls.

    Args:
        url: URL of the website to call
        headers: Optional headers (e.g., fake User Agent)

    Returns:
        response: Response from the website (requests.get)
    """
    sf = SessionFactory()
    session = sf.get()

    # Retry setup
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))

    # Default User-Agent
    ua_header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36"
    }
    headers = {**headers, **ua_header} if headers else ua_header

    try:
        logger.info(f"Sending request to {url}")
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response
    except HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
    except RequestException as req_err:
        logger.error(f"Request error occurred: {req_err}")
    return None
