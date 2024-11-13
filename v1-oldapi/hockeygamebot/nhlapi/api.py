"""
Single module to call the NHL API.
"""

import logging

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, RequestException

from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.sessions import SessionFactory


def nhl_api(endpoint):
    urls = utils.load_urls()
    api_base = urls["endpoints"]["nhl_endpoint"]

    sf = SessionFactory()
    session = sf.get()

    retries = HTTPAdapter(max_retries=3)
    session.mount("https://", retries)
    session.mount("http://", retries)

    # Fix issues with leading slash on an endpoint call
    url = f"{api_base}{endpoint}" if endpoint[0] == "/" else f"{api_base}/{endpoint}"

    try:
        logging.info("Sending Stats API Request - %s", url)
        response = session.get(url, timeout=5)
        return response
    except ConnectionError as ce:
        logging.error(ce)
        return None
    except RequestException as re:
        logging.error(re)
        return None


def nhl_rpt(endpoint):
    urls = utils.load_urls()
    api_base = urls["endpoints"]["nhl_rpt_base"]

    sf = SessionFactory()
    session = sf.get()

    retries = HTTPAdapter(max_retries=3)
    session.mount("https://", retries)
    session.mount("http://", retries)

    url = f"{api_base}{endpoint}"

    try:
        logging.info("Sending Report API Request - %s", url)
        response = session.get(url, timeout=5)
        return response
    except ConnectionError as ce:
        logging.error(ce)
        return None
    except RequestException as re:
        logging.error(re)
        return None


def nhl_score_rpt(endpoint):
    urls = utils.load_urls()
    api_base = urls["endpoints"]["nhl_score_rpt_base"]

    sf = SessionFactory()
    session = sf.get()

    retries = HTTPAdapter(max_retries=3)
    session.mount("https://", retries)
    session.mount("http://", retries)

    url = f"{api_base}{endpoint}"

    try:
        logging.info("Sending Score Report Request - %s", url)
        response = session.get(url, timeout=5)
        return response if response.status_code == 200 else None
    except ConnectionError as ce:
        logging.error(ce)
        return None
    except RequestException as re:
        logging.error(re)
        return None
