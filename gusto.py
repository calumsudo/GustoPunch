import rumps
import os
import json
import time
import logging
import threading
import atexit
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.expanduser("~/.gusto_clock.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("GustoPunch")


class GustoPunchApp(rumps.App):
    def __init__(self):
        # Initial state
        self.status = "unknown"
        self.clock_in_time = None
        super(GustoPunchApp, self).__init__("⏱", quit_button=None)

        # Browser session
        self.driver = None
        self.driver_lock = threading.Lock()
        self.session_active = False

        # Create the clock action items
        self.clock_in_item = rumps.MenuItem("Clock In", callback=self.clock_in)
        self.clock_out_item = rumps.MenuItem("Clock Out", callback=self.clock_out)

        # Setup initial menu items with both clock actions
        self.menu = [
            self.clock_in_item,
            self.clock_out_item,
            None,  # Separator
            rumps.MenuItem("Time Clocked: --:--", callback=None),
            None,  # Separator
            rumps.MenuItem("Check Status", callback=self.check_status_clicked),
            rumps.MenuItem("Setup", callback=self.setup),
            rumps.MenuItem("Restart Session", callback=self.restart_browser_session),
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        # Configuration
        self.config_file = os.path.expanduser("~/.gusto_punch_config.json")
        self.config = self.load_config()

        # Load saved clock-in time if exists
        self.load_timer_state()

        # Start timer update
        rumps.Timer(self.update_timer, 60).start()  # Update every minute

        # Check if setup is needed
        if not self.is_configured():
            self.setup(None)
        else:
            # Initialize browser session and check status
            self.init_browser_session()

        # Set initial menu state
        self.update_menu_state()

        # Register cleanup function
        atexit.register(self.cleanup)

    def cleanup(self):
        """Clean up resources when app exits"""
        self.close_browser_session()

    def init_browser_session(self):
        """Initialize a persistent browser session"""
        with self.driver_lock:
            try:
                if self.driver is not None:
                    # Try to check if driver is still responsive
                    try:
                        self.driver.current_url  # This will throw an exception if the driver is no longer active
                        self.session_active = True
                        logger.info("Existing browser session is still active")
                        return True
                    except (WebDriverException, Exception) as e:
                        logger.warning(
                            f"Existing browser session is stale, creating new one: {e}"
                        )
                        try:
                            self.driver.quit()
                        except Exception:
                            pass
                        self.driver = None

                logger.info("Initializing new browser session")
                self.driver = self.get_chrome_driver()
                self.session_active = True

                # Navigate to Gusto and log in
                self.driver.get("https://app.gusto.com/login")

                if self.handle_login(self.driver):
                    logger.info("Login successful, browser session initialized")
                    # Check status
                    self.check_status_from_driver(self.driver)
                    return True
                else:
                    logger.error("Login failed during session initialization")
                    self.close_browser_session()
                    return False

            except Exception as e:
                logger.error(f"Error initializing browser session: {e}")
                self.close_browser_session()
                return False

    def close_browser_session(self):
        """Close the browser session"""
        with self.driver_lock:
            if self.driver is not None:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                self.session_active = False
                logger.info("Browser session closed")

    def restart_browser_session(self, _):
        """Menu callback to restart the browser session"""
        self.close_browser_session()
        success = self.init_browser_session()
        if success:
            rumps.notification(
                "Gusto Punch", "Session", "Browser session restarted", sound=False
            )
        else:
            rumps.notification(
                "Gusto Punch",
                "Session",
                "Failed to restart browser session",
                sound=False,
            )

    def update_menu_state(self):
        """Update the menu to show only the relevant clock action"""
        # Toggle visibility of clock actions based on status
        if self.status == "out":
            self.clock_in_item.set_callback(self.clock_in)
            self.clock_out_item.set_callback(None)  # Disable the item
        elif self.status == "in":
            self.clock_in_item.set_callback(None)  # Disable the item
            self.clock_out_item.set_callback(self.clock_out)
        else:
            # If status is unknown, enable both options
            self.clock_in_item.set_callback(self.clock_in)
            self.clock_out_item.set_callback(self.clock_out)

    def load_timer_state(self):
        """Load saved timer state"""
        try:
            timer_file = os.path.expanduser("~/.gusto_punch_timer.json")
            if os.path.exists(timer_file):
                with open(timer_file, "r") as f:
                    data = json.load(f)
                    if data.get("clock_in_time"):
                        self.clock_in_time = float(data["clock_in_time"])
                        self.update_timer(None)  # Update display immediately
        except Exception as e:
            logger.error(f"Error loading timer state: {e}")

    def save_timer_state(self):
        """Save timer state"""
        try:
            timer_file = os.path.expanduser("~/.gusto_punch_timer.json")
            with open(timer_file, "w") as f:
                json.dump({"clock_in_time": self.clock_in_time}, f)
        except Exception as e:
            logger.error(f"Error saving timer state: {e}")

    def update_timer(self, _):
        """Update the timer display"""
        if self.status == "in" and self.clock_in_time:
            elapsed_seconds = time.time() - self.clock_in_time
            hours = int(elapsed_seconds // 3600)
            minutes = int((elapsed_seconds % 3600) // 60)
            self.menu[
                "Time Clocked: --:--"
            ].title = f"Time Clocked: {hours:02d}:{minutes:02d}"
        else:
            self.menu["Time Clocked: --:--"].title = "Time Clocked: --:--"

    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading configuration: {e}")
                rumps.alert(f"Error loading configuration: {e}")
                return {}
        return {}

    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f)
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            rumps.alert(f"Error saving configuration: {e}")

    def is_configured(self):
        """Check if app is configured"""
        return "email" in self.config and "password" in self.config

    def setup(self, _):
        """Show setup dialog"""
        # Get email
        response = rumps.Window(
            "Please enter your Gusto email:",
            "Gusto Punch Setup",
            dimensions=(320, 100),
            ok="Next",
            cancel="Cancel",
        ).run()

        if response.clicked:
            email = response.text.strip()

            # Now get password
            response = rumps.Window(
                "Please enter your Gusto password:",
                "Gusto Punch Setup",
                dimensions=(320, 100),
                secure=True,
                ok="Save",
                cancel="Cancel",
            ).run()

            if response.clicked:
                password = response.text.strip()

                if email and password:
                    self.config["email"] = email
                    self.config["password"] = password
                    self.save_config()

                    # Close any existing session
                    self.close_browser_session()

                    # First-time login to set up profile and handle 2FA
                    self.first_time_login()
                else:
                    rumps.alert("Email and password are required")

    def first_time_login(self):
        """Perform first-time login to set up browser profile and handle 2FA"""
        temp_driver = None
        try:
            temp_driver = self.get_chrome_driver()

            # Navigate to login page
            temp_driver.get("https://app.gusto.com/login")

            # Fill email
            email_input = WebDriverWait(temp_driver, 10).until(
                EC.presence_of_element_located((By.NAME, "email"))
            )
            email_input.send_keys(self.config["email"])

            # Find submit button
            continue_button = WebDriverWait(temp_driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            continue_button.click()

            # Wait for password field
            password_input = WebDriverWait(temp_driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='password']")
                )
            )
            password_input.send_keys(self.config["password"])
            
            # Check for Remember this device checkbox and select it
            try:
                remember_checkbox = WebDriverWait(temp_driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='checkbox'][name='remember']"))
                )
                if not remember_checkbox.is_selected():
                    remember_checkbox.click()
                    logger.info("Selected 'Remember this device' checkbox")
            except TimeoutException:
                logger.info("No 'Remember this device' checkbox found on password page")

            # Find submit button
            submit_button = WebDriverWait(temp_driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            submit_button.click()

            # Check if 2FA is needed
            try:
                code_input = WebDriverWait(temp_driver, 5).until(
                    EC.presence_of_element_located((By.NAME, "code"))
                )

                # Prompt for 2FA code
                response = rumps.Window(
                    "Please enter your 6-digit verification code:",
                    "Gusto 2FA",
                    dimensions=(320, 100),
                    ok="Submit",
                    cancel="Cancel",
                ).run()

                if response.clicked:
                    code = response.text.strip()
                    if code:
                        code_input.send_keys(code)
                        
                        # Check for Remember this device checkbox on 2FA page and select it
                        try:
                            remember_checkbox = WebDriverWait(temp_driver, 3).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='checkbox'][name='remember']"))
                            )
                            if not remember_checkbox.is_selected():
                                remember_checkbox.click()
                                logger.info("Selected 'Remember this device' checkbox on 2FA page")
                        except TimeoutException:
                            logger.info("No 'Remember this device' checkbox found on 2FA page")
                        
                        submit_button = temp_driver.find_element(
                            By.CSS_SELECTOR, "button[type='submit']"
                        )
                        submit_button.click()

                        # Check for Remember Device page after 2FA
                        self.handle_remember_device_page(temp_driver)

                        # Wait for successful login
                        WebDriverWait(temp_driver, 10).until(
                            EC.presence_of_element_located(
                                (
                                    By.CSS_SELECTOR,
                                    "[data-dd-action-name='Clock in'], [data-dd-action-name='Clock out']",
                                )
                            )
                        )

                        # Update status after successful login
                        self.check_status_from_driver(temp_driver)

                        rumps.alert(
                            "Setup complete! You can now use the app to clock in and out."
                        )
                    else:
                        rumps.alert("Verification code is required")
                else:
                    return
            except TimeoutException:
                # No 2FA needed or we're already logged in
                
                # Check for Remember Device page after login
                self.handle_remember_device_page(temp_driver)
                
                try:
                    WebDriverWait(temp_driver, 10).until(
                        EC.presence_of_element_located(
                            (
                                By.CSS_SELECTOR,
                                "[data-dd-action-name='Clock in'], [data-dd-action-name='Clock out']",
                            )
                        )
                    )

                    # Update status after successful login
                    self.check_status_from_driver(temp_driver)

                    rumps.alert(
                        "Setup complete! You can now use the app to clock in and out."
                    )
                except TimeoutException:
                    rumps.alert(
                        "Could not verify successful login. Please check your credentials."
                    )

            # Initialize persistent session
            self.close_browser_session()
            self.init_browser_session()

        except Exception as e:
            logger.error(f"Error during setup: {e}")
            rumps.alert(f"Error during setup: {e}")
        finally:
            # Close the temporary driver
            if temp_driver:
                try:
                    temp_driver.quit()
                except Exception:
                    pass

    def handle_remember_device_page(self, driver):
        """Handle the 'Remember this device' page that may appear after 2FA"""
        try:
            # Look for the Remember this device button
            remember_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(), 'Remember this device')]]"))
            )
            logger.info("Found 'Remember this device' button, clicking it")
            remember_btn.click()
            # Give it a moment to process
            time.sleep(1)
            return True
        except TimeoutException:
            logger.info("No 'Remember this device' page found, continuing...")
            return False
        except Exception as e:
            logger.error(f"Error handling remember device page: {e}")
            return False

    def get_chrome_driver(self):
        """Configure and return Chrome driver with user profile"""
        options = Options()

        # Set up user data directory
        user_data_dir = os.path.expanduser("~/.gusto_punch_chrome_profile")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        options.add_argument(f"user-data-dir={user_data_dir}")

        # Headless mode configuration
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Add user agent to appear more like a regular browser
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Enable logging
        options.add_argument("--enable-logging")
        options.add_argument("--v=1")

        # Use webdriver_manager to automatically download the correct driver
        try:
            # Use ChromeDriverManager to get the appropriate driver
            ChromeDriverManager().install()  # This installs the driver in the cache
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            logger.warning(f"Error using ChromeDriverManager: {e}")
            # Fallback to the default Chrome driver path
            driver = webdriver.Chrome(options=options)

        # Update the navigator.webdriver flag to help avoid detection
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Set page load timeout
        driver.set_page_load_timeout(30)

        return driver

    def handle_login(self, driver):
        """Handle the login process with enhanced email field detection"""
        try:
            logger.info("Starting login process")

            # First check if we're already logged in
            try:
                logger.info("Checking if already logged in...")
                wait = WebDriverWait(driver, 3, poll_frequency=0.1)
                wait.until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "[data-dd-action-name='Clock in'], [data-dd-action-name='Clock out']",
                        )
                    )
                )
                logger.info("Already logged in!")
                return True
            except TimeoutException:
                logger.info("Not logged in, proceeding with login...")

            # Wait for page to be interactive
            wait = WebDriverWait(driver, 5, poll_frequency=0.1)
            wait.until(
                lambda d: d.execute_script("return document.readyState") != "loading"
            )
            logger.info("Page interactive")

            # Log current URL
            logger.info(f"Current URL: {driver.current_url}")

            # Check if email field exists
            try:
                logger.info("Looking for email field...")
                wait = WebDriverWait(driver, 3, poll_frequency=0.1)
                email_input = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "input[name='email']")
                    )
                )
                logger.info("Found email field, entering email")
                email_input.clear()
                email_input.send_keys(self.config["email"])

                # Look for Continue button after email
                continue_button = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button[type='submit']")
                    )
                )
                continue_button.click()
                logger.info("Submitted email, proceeding to password")

                # Short wait for password field to appear
                time.sleep(1)
            except TimeoutException:
                logger.info("No email field found, assuming returning user flow")

            # Now look for password field
            try:
                logger.info("Looking for password field...")
                wait = WebDriverWait(driver, 5, poll_frequency=0.1)
                password_input = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "input[type='password']")
                    )
                )
                logger.info("Found password field")

                # Enter password
                password_input.clear()
                password_input.send_keys(self.config["password"])
                logger.info("Password entered")

                # Check for Remember this device checkbox and select it
                try:
                    remember_checkbox = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='checkbox'][name='remember']"))
                    )
                    if not remember_checkbox.is_selected():
                        remember_checkbox.click()
                        logger.info("Selected 'Remember this device' checkbox")
                except TimeoutException:
                    logger.info("No 'Remember this device' checkbox found on password page")

                # Look for Continue/Submit button
                logger.info("Looking for submit button...")
                submit_button = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button[type='submit']")
                    )
                )
                submit_button.click()
                logger.info("Clicked submit button")

                # Handle 2FA if needed
                try:
                    code_input = wait.until(
                        EC.presence_of_element_located((By.NAME, "code"))
                    )
                    logger.info("2FA required")

                    response = rumps.Window(
                        "Please enter your 6-digit verification code:",
                        "Gusto 2FA",
                        dimensions=(320, 100),
                        ok="Submit",
                        cancel="Cancel",
                    ).run()

                    if response.clicked:
                        code = response.text.strip()
                        if code:
                            code_input.send_keys(code)
                            
                            # Check for Remember this device checkbox on 2FA page and select it
                            try:
                                remember_checkbox = wait.until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='checkbox'][name='remember']"))
                                )
                                if not remember_checkbox.is_selected():
                                    remember_checkbox.click()
                                    logger.info("Selected 'Remember this device' checkbox on 2FA page")
                            except TimeoutException:
                                logger.info("No 'Remember this device' checkbox found on 2FA page")
                            
                            submit_button = driver.find_element(
                                By.CSS_SELECTOR, "button[type='submit']"
                            )
                            submit_button.click()
                            logger.info("2FA code submitted")
                            
                            # Check for Remember Device page after 2FA
                            self.handle_remember_device_page(driver)
                        else:
                            logger.error("Empty 2FA code provided")
                            return False
                    else:
                        logger.error("2FA code entry cancelled")
                        return False

                except TimeoutException:
                    logger.info("No 2FA required")
                
                # Check for Remember Device page after login/2FA
                self.handle_remember_device_page(driver)

                # Wait for successful login
                try:
                    wait = WebDriverWait(driver, 10, poll_frequency=0.1)
                    wait.until(
                        EC.presence_of_element_located(
                            (
                                By.CSS_SELECTOR,
                                "[data-dd-action-name='Clock in'], [data-dd-action-name='Clock out']",
                            )
                        )
                    )
                    logger.info("Successfully logged in!")
                    return True
                except TimeoutException:
                    logger.error("Could not verify successful login")
                    return False

            except TimeoutException:
                return False

        except Exception as e:
            logger.error(f"Error during login: {e}")
            try:
                logger.error("Error during login")
            except Exception:
                pass
            rumps.alert(f"Error during login: {e}")
            return False

    def check_status_clicked(self, _):
        """Menu callback for manual status check"""
        if not self.session_active and not self.init_browser_session():
            rumps.notification(
                "Gusto Punch",
                "Error",
                "Failed to initialize browser session",
                sound=False,
            )
            return

        self.check_status()
        rumps.notification(
            "Gusto Punch", "Status", f"Currently clocked {self.status}", sound=False
        )

    def check_status(self):
        """Check if currently clocked in or out and update the menu"""
        with self.driver_lock:
            try:
                if not self.is_configured():
                    return

                if not self.session_active:
                    if not self.init_browser_session():
                        return

                # Ensure we're on the dashboard
                try:
                    self.driver.get("https://app.gusto.com/dashboard")
                    # Wait for the page to load
                    WebDriverWait(self.driver, 10).until(
                        lambda d: d.execute_script("return document.readyState")
                        == "complete"
                    )
                except Exception as e:
                    logger.error(f"Error navigating to dashboard: {e}")
                    # Try to refresh and login again if needed
                    if not self.init_browser_session():
                        return

                # Check status from the dashboard
                self.check_status_from_driver(self.driver)

            except Exception as e:
                logger.error(f"Error checking status: {e}")
                self.status = "unknown"
                self.title = "⏱"
                # Try to re-initialize the session
                self.close_browser_session()
                self.init_browser_session()

    def check_status_from_driver(self, driver):
        """Check status from an already logged in driver"""
        try:
            # Check for clock in button
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-dd-action-name='Clock in']")
                )
            )
            # If we're here, clock in button is present, meaning we're clocked out
            self.status = "out"
            self.title = "⏱☒"
            self.clock_in_time = None
            self.save_timer_state()
            self.update_timer(None)
            self.update_menu_state()  # Update menu after status change
        except TimeoutException:
            try:
                # Check for clock out button
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "[data-dd-action-name='Clock out']")
                    )
                )
                # If we're here, clock out button is present, meaning we're clocked in
                self.status = "in"
                self.title = "⏱☑"
                # Only set clock_in_time if it's not already set
                if not self.clock_in_time:
                    self.clock_in_time = time.time()
                    self.save_timer_state()
                self.update_timer(None)
                self.update_menu_state()  # Update menu after status change
            except TimeoutException:
                # Neither button found
                # Check for "Remember this device" page before giving up
                if self.handle_remember_device_page(driver):
                    # Try again after handling remember device page
                    self.check_status_from_driver(driver)
                else:
                    self.status = "unknown"
                    self.title = "⏱"
                    self.clock_in_time = None
                    self.save_timer_state()
                    self.update_timer(None)
                    self.update_menu_state()  # Update menu after status change

    def clock_in(self, _):
        """Clock in to Gusto"""
        if self.clock_in_item.callback:  # Only proceed if callback is active
            self.clock_action("in")

    def clock_out(self, _):
        """Clock out of Gusto"""
        if self.clock_out_item.callback:  # Only proceed if callback is active
            self.clock_action("out")

    def clock_action(self, action_type):
        """Perform clock in/out action"""
        with self.driver_lock:
            try:
                if not self.is_configured():
                    rumps.alert("Please complete setup first")
                    return

                action_text = "in" if action_type == "in" else "out"
                self.notification = rumps.notification(
                    "Gusto Punch", "Status", f"Clocking {action_text}...", sound=False
                )

                if not self.session_active:
                    if not self.init_browser_session():
                        rumps.notification(
                            "Gusto Punch",
                            "Error",
                            "Failed to initialize browser session",
                            sound=False,
                        )
                        return

                # Ensure we're on the dashboard
                try:
                    self.driver.get("https://app.gusto.com/dashboard")
                except Exception as e:
                    logger.error(f"Error navigating to dashboard: {e}")
                    # Try to refresh and login again if needed
                    if not self.init_browser_session():
                        rumps.notification(
                            "Gusto Punch",
                            "Error",
                            "Failed to navigate to dashboard",
                            sound=False,
                        )
                        return

                # Check for "Remember this device" page
                self.handle_remember_device_page(self.driver)

                # Wait for clock in/out button
                selector = f"[data-dd-action-name='Clock {action_text}']"
                try:
                    # Create a WebDriverWait with shorter polling interval
                    wait = WebDriverWait(self.driver, 10, poll_frequency=0.1)
                    clock_button = wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )

                    # Click clock button
                    clock_button.click()

                    # Wait for the status to update
                    wait.until(
                        lambda d: d.find_elements(By.CSS_SELECTOR, selector) == []
                        or not d.find_element(By.CSS_SELECTOR, selector).is_displayed()
                    )

                    # Update status and timer
                    self.status = action_type
                    self.title = "⏱☑" if action_type == "in" else "⏱☒"
                    if action_type == "in":
                        self.clock_in_time = time.time()
                    else:
                        self.clock_in_time = None
                    self.save_timer_state()
                    self.update_timer(None)

                    # Update menu state to reflect new status
                    self.update_menu_state()

                    rumps.notification(
                        "Gusto Punch",
                        "Success",
                        f"Clocked {action_text} successfully",
                        sound=False,
                    )
                except TimeoutException:
                    # Button not found
                    if action_type == "in" and self.status == "in":
                        rumps.notification(
                            "Gusto Punch", "Info", "Already clocked in", sound=False
                        )
                    elif action_type == "out" and self.status == "out":
                        rumps.notification(
                            "Gusto Punch", "Info", "Already clocked out", sound=False
                        )
                    else:
                        rumps.alert(f"Could not find clock {action_text} button")
                        # Try refreshing the session
                        self.restart_browser_session(None)

            except Exception as e:
                logger.error(f"Error clocking {action_text}: {e}")
                rumps.alert(f"Error clocking {action_text}: {e}")
                # Try to re-initialize the session
                self.close_browser_session()
                self.init_browser_session()

    def quit_app(self, _):
        """Quit the application"""
        self.close_browser_session()
        rumps.quit_application()


if __name__ == "__main__":
    GustoPunchApp().run()