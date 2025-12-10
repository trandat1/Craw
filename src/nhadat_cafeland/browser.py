from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

# Chrome
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService

# Edge
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService


def init_driver(         
    debugger_address: str,
    page_load_timeout: int,
    wait_timeout: int,
    browser: str = "chrome",  # "chrome" hoặc "edge"
):
    browser = browser.lower()

    if browser == "chrome":
        options = ChromeOptions()
        options.add_experimental_option("debuggerAddress", debugger_address)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--start-maximized")

        driver = webdriver.Chrome(options=options)

    elif browser == "edge":
        options = EdgeOptions()
        options.add_experimental_option("debuggerAddress", debugger_address)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--start-maximized")

        driver = webdriver.Edge(options=options)

    else:
        raise ValueError(f"Unsupported browser: {browser}")

    # Timeout setup
    driver.set_page_load_timeout(page_load_timeout)
    wait = WebDriverWait(driver, wait_timeout)

    return driver, wait
