import contextlib
import getpass
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
import traceback
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from requests_cache import CachedSession as CSession
from requests_ratelimiter import LimiterAdapter

from getmyancestors.classes.translation import translations

DEFAULT_CLIENT_ID = "a02j000000KTRjpAAH"
DEFAULT_REDIRECT_URI = "https://misbach.github.io/fs-auth/index_raw.html"


class SecureLogFilter(logging.Filter):
    """Filter to censor sensitive data in logs"""

    SENSITIVE_RE = re.compile(
        r"(Authorization: Bearer |Cookie: |XSRF-TOKEN=|SESSION=|password=|_csrf=|username=)[^ \r\n&]+"
    )

    def filter(self, record):
        if isinstance(record.msg, (str, bytes)):
            msg = (
                record.msg
                if isinstance(record.msg, str)
                else record.msg.decode("utf-8", "ignore")
            )
            record.msg = self.SENSITIVE_RE.sub(r"\1***", msg)
        return True


LICENSE_AGREEMENT = """
================================================================================
                    getmyancestors - License & Terms of Use
================================================================================

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

By using this software to access FamilySearch, you also agree to:

1. Comply with FamilySearch's Terms of Use (https://www.familysearch.org/terms)
2. Not abuse the API through excessive requests or automated scraping
3. If you experience a bug or a network loop, close the program and file a bug!
4. Only use the tool for personal, non-commercial purposes.
5. Respect the privacy of living individuals in any downloaded data
6. Accept that FamilySearch may revoke API access for violations

DO NOT USE THE TOOL EXCESSIVELY!
DOWNLOAD YOUR FAMILY'S GEDCOM AND USE IT OFFLINE.
BE RESPECTFUL OF FAMILYSEARCH'S SERVERS AND RESPECT THEIR TERMS OF USE.

================================================================================
"""


class GMASession(requests.Session):
    """Create a FamilySearch session
    :param username and password: valid FamilySearch credentials
    :param verbose: True to active verbose mode
    :param logfile: a file object or similar
    :param timeout: time before retry a request
    """

    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(
        self,
        username,
        password,
        client_id=None,
        redirect_uri=None,
        verbose=False,
        logfile=None,
        timeout=60,
        requests_per_second=5,
    ):
        requests.Session.__init__(self)
        self.username = username
        self.password = password
        self.lock = threading.Lock()
        self.client_id = client_id or DEFAULT_CLIENT_ID
        if redirect_uri:
            self.redirect_uri = redirect_uri
        else:
            self.redirect_uri = DEFAULT_REDIRECT_URI
            # Warn about using fallback redirect URI - check TTY before coloring
            # Suppress in offline mode as we don't login
            if not os.environ.get("GMA_OFFLINE_MODE"):
                use_color = sys.stderr.isatty() or os.environ.get("FORCE_COLOR", "")
                msg = (
                    "⚠  WARNING: Using fallback redirect URI (misbach.github.io)\n"
                    "   This is a third-party OAuth callback. Consider registering your own.\n"
                    "   See: https://www.familysearch.org/developers/\n"
                )
                if use_color:
                    sys.stderr.write(f"\033[33m{msg}\033[0m")
                else:
                    sys.stderr.write(msg)
        self.verbose = verbose
        self.logfile = logfile
        self.timeout = timeout
        self.fid = None
        self.lang = None
        self.display_name = None
        self.counter = 0

        # Persistence setup - use ~/.cache/getmyancestors/ by default
        cache_dir = os.environ.get(
            "GMA_CACHE_DIR", os.path.expanduser("~/.cache/getmyancestors")
        )
        os.makedirs(cache_dir, exist_ok=True)
        self.db_path = os.path.join(cache_dir, "session.sqlite")
        # Cookie file is now stored in cache directory too
        self.cookie_file = os.path.join(cache_dir, "cookies.json")
        self._init_db()
        self.check_license()

        # Debug logging toggle
        # Debug logging toggle
        if os.environ.get("GMA_DEBUG"):
            logger = logging.getLogger()
            logger.setLevel(logging.DEBUG)
            # Add secure filter
            secure_filter = SecureLogFilter()
            for handler in logger.handlers:
                handler.addFilter(secure_filter)
            if not logger.handlers:
                handler = logging.StreamHandler(sys.stderr)
                handler.addFilter(secure_filter)
                logger.addHandler(handler)

            # Optional: Enable full HTTP level logging if GMA_TRACE is set
            if os.environ.get("GMA_TRACE"):
                import http.client as http_client  # pylint: disable=import-outside-toplevel

                http_client.HTTPConnection.debuglevel = 1
                self.write_log(
                    "🐞 TRACE MODE ENABLED - WARNING: Logs will contain sensitive data unless filtered by SecureLogFilter."
                )

            self.write_log("🐞 DEBUG MODE ENABLED - Censored logging active.")

        # Hardcode robust User-Agent to avoid bot detection
        with self.lock:
            self.headers.update(self.DEFAULT_HEADERS)

        # Apply a rate-limit (default 5 requests per second) to all requests
        # Credit: Josemando Sobral
        adapter = LimiterAdapter(per_second=requests_per_second)
        self.mount("https://", adapter)

        # Defer login to subclasses to ensure initialization is complete
        # self.login()

    def _init_db(self):
        """Initialize SQLite database for session storage"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS session (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.commit()

    def check_license(self):
        """Check if user has accepted the current license agreement"""
        # Allow tests/CI to bypass this check explicitly
        if os.environ.get("GMA_I_RESPECT_FAMILYSEARCH_PLEASE_SUPPRESS_LICENSE_PROMPT"):
            return

        # Hash combines license text AND username so acceptance is per-user
        current_hash = hashlib.sha256(
            (LICENSE_AGREEMENT + self.username).encode("utf-8")
        ).hexdigest()
        accepted_hash = None

        # 1. Check external license file
        # We store license acceptance in a separate JSON file so it survives cache clearing
        license_file = os.path.join(
            os.path.dirname(self.db_path), "..", "license-agreement.json"
        )
        license_file = os.path.abspath(license_file)

        if os.path.exists(license_file):
            try:
                with open(license_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("license_hash") == current_hash:
                        accepted_hash = data["license_hash"]
            except Exception:
                pass  # Ignore file errors

        if accepted_hash == current_hash:
            return

        # 2. Prompt user if mismatch (NO lock held)
        if not sys.stdin.isatty():
            sys.stderr.write(
                "ERROR: License agreement has changed or not yet been accepted.\n"
                "Please run this tool interactively to accept the license.\n"
            )
            sys.exit(1)

        print(LICENSE_AGREEMENT)
        try:
            response = (
                input("Do you agree to the terms above? (yes/no): ").strip().lower()
            )
            if response != "yes":
                print("License not accepted. Exiting.")
                sys.exit(1)

            # 3. Write new hash to JSON file
            try:
                data = {"license_hash": current_hash}
                with open(license_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as e:
                # Fallback or just print warning if we can't save
                if self.verbose:
                    print(
                        f"Warning: Could not save license agreement to {license_file}: {e}"
                    )

            print("License accepted.\n")

        except (EOFError, KeyboardInterrupt):
            print("\nLicense acceptance cancelled. Exiting.")
            sys.exit(1)

    @property
    def logged(self):
        with self.lock:
            return bool(
                self.cookies.get("fssessionid") or self.headers.get("Authorization")
            )

    def save_cookies(self):
        """save cookies and authorization header to JSON (explicitly NOT sqlite for security)"""
        try:
            with self.lock:
                cookies_export = requests.utils.dict_from_cookiejar(self.cookies)
                auth_header = self.headers.get("Authorization")

            data = {
                "cookies": cookies_export,
                "auth": auth_header,
            }
            # Save to separate JSON file
            cookie_file = os.path.join(
                os.path.dirname(self.db_path), "..", "cookies.json"
            )
            cookie_file = os.path.abspath(cookie_file)

            with open(cookie_file, "w", encoding="utf-8") as f:
                json.dump(data, f)

            if self.verbose:
                self.write_log("Session saved to JSON: " + cookie_file)
        except Exception as e:
            self.write_log("Error saving session: " + str(e))

    def load_cookies(self):
        """load cookies and authorization header from JSON"""
        cookie_file = os.path.join(os.path.dirname(self.db_path), "..", "cookies.json")
        cookie_file = os.path.abspath(cookie_file)

        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._apply_session_data(data)
                    if self.verbose:
                        self.write_log("Session loaded from JSON: " + cookie_file)
                    return True
            except Exception as e:
                self.write_log("Error loading session from JSON: " + str(e))

        # 2. Legacy Migration: checking old cookie file if it exists
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._apply_session_data(data)
                # We do NOT auto-save to new JSON here to respect read-only/security.
                # It will save to new JSON only on next login/save_cookies call.
                if self.verbose:
                    self.write_log(
                        "Session loaded (migrated) from legacy JSON: "
                        + self.cookie_file
                    )
                return True
            except Exception as e:
                self.write_log("Error loading legacy cookie file: " + str(e))

        return False

    def _apply_session_data(self, data):
        """Internal helper to apply session dict to current session"""
        if isinstance(data, dict) and ("cookies" in data or "auth" in data):
            cookies_dict = data.get("cookies", {})
            auth_header = data.get("auth")
        else:
            cookies_dict = data
            auth_header = None

        with self.lock:
            self.cookies.update(requests.utils.cookiejar_from_dict(cookies_dict))
            if auth_header:
                self.headers.update({"Authorization": auth_header})

    # ANSI color codes for terminal output
    COLOR_RESET = "\033[0m"
    COLOR_RED = "\033[91m"
    COLOR_YELLOW = "\033[93m"

    def write_log(self, text, level="info"):
        """write text in the log file with optional color"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log = f"[{timestamp}]: {text}\n"

        if self.verbose:
            # Apply color if TTY or FORCE_COLOR is set (for piped output like tee)
            use_color = sys.stderr.isatty() or os.environ.get("FORCE_COLOR", "")
            if level == "error" and use_color:
                sys.stderr.write(f"{self.COLOR_RED}{log}{self.COLOR_RESET}")
            elif level == "warning" and use_color:
                sys.stderr.write(f"{self.COLOR_YELLOW}{log}{self.COLOR_RESET}")
            else:
                sys.stderr.write(log)

        if self.logfile:
            self.logfile.write(log)  # No color in log files

    # pylint: disable=inconsistent-return-statements
    def login(self):
        """retrieve FamilySearch session ID
        (https://familysearch.org/developers/docs/guides/oauth2)
        """
        if self.load_cookies():
            if self.verbose:
                self.write_log("Attempting to reuse cached session...")
            # Use auto_login=False to prevent recursion if session is invalid
            # Force network verification to prevent infinite loops with stale cache
            context = (
                self.cache_disabled()
                if hasattr(self, "cache_disabled")
                else contextlib.nullcontext()
            )
            with context:
                self.set_current(auto_login=False)
            if self.logged and self.fid:
                if self.verbose:
                    self.write_log("Successfully reused cached session.")
                return True
            if self.verbose:
                self.write_log("Cached session invalid or expired.")

        # Define context manager for disabling cache
        if hasattr(self, "cache_disabled"):
            cache_context = self.cache_disabled()
        else:
            cache_context = contextlib.nullcontext()

        with cache_context:
            try:
                if not self.username or not self.password:
                    return self.manual_login()

                # Clear cookies to ensure fresh start for new login
                with self.lock:
                    self.cookies.clear()

                url = "https://www.familysearch.org/auth/familysearch/login"
                self.write_log("Downloading: " + url)

                # Use the temp session for requests
                self.get(url, headers=self.headers, timeout=self.timeout)
                xsrf = self.cookies.get("XSRF-TOKEN")
                if not xsrf:
                    self.write_log("No XSRF token found. Switching to manual login.")
                    return self.manual_login()

                url = "https://ident.familysearch.org/login"
                self.write_log("Downloading: " + url)
                res = self.post(
                    url,
                    data={
                        "_csrf": xsrf,
                        "username": self.username,
                        "password": self.password,
                    },
                    headers=self.headers,
                    timeout=self.timeout,
                )

                try:
                    data = res.json()
                except ValueError:
                    self.write_log(f"Headless Login Failed. Status: {res.status_code}")
                    self.write_log(f"Response Preview: {res.text[:200]}")
                    self.write_log("Switching to manual login.")
                    return self.manual_login()

                if "redirectUrl" not in data:
                    self.write_log("Redirect URL not found in response.")
                    return self.manual_login()

                url = data["redirectUrl"]
                self.write_log("Downloading: " + url)
                self.get(url, headers=self.headers, timeout=self.timeout)

                params = urlencode(
                    {
                        "response_type": "code",
                        "scope": "openid profile email qualifies_for_affiliate_account country",
                        "client_id": self.client_id,
                        "redirect_uri": self.redirect_uri,
                        "username": self.username,
                    }
                )
                url = f"https://ident.familysearch.org/cis-web/oauth2/v3/authorization?{params}"
                self.write_log("Downloading: " + url)

                # Allow redirects so we follow the chain to the callback URI
                response = self.get(
                    url,
                    allow_redirects=True,
                    headers=self.headers,
                    timeout=self.timeout,
                )

                # Check if we landed on the redirect URI (or have the code in the URL)
                final_url = response.url
                code = None

                if "code=" in final_url:
                    code = parse_qs(urlparse(final_url).query).get("code")

                # If not in final URL, check history (in case of a meta refresh or stop)
                if not code and response.history:
                    for resp in response.history:
                        if "code=" in resp.headers.get("Location", ""):
                            code = parse_qs(
                                urlparse(resp.headers["Location"]).query
                            ).get("code")
                            if code:
                                break

                if not code:
                    self.write_log(f"Code not found in URL: {final_url}")
                    return self.manual_login(response.url)

                if isinstance(code, list):
                    code_str = code[0]
                else:
                    code_str = code

                # Use raw requests to avoid cache interference just in case
                url = "https://ident.familysearch.org/cis-web/oauth2/v3/token"
                self.write_log("Downloading: " + url)
                res = requests.post(
                    url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self.client_id,
                        "code": code_str,
                        "redirect_uri": self.redirect_uri,
                    },
                    headers=self.headers,
                    timeout=self.timeout,
                )

                data = res.json()
                if "access_token" in data:
                    with self.lock:
                        self.headers.update(
                            {"Authorization": f"Bearer {data['access_token']}"}
                        )
                    self.set_current(auto_login=False)
                    if self.logged:
                        self.save_cookies()
                        return True
            except Exception as e:
                self.write_log("Headless login error: " + str(e))
                self.write_log(traceback.format_exc())
                return self.manual_login()

    # pylint: disable=inconsistent-return-statements
    def manual_login(self, auth_url=None):
        """Perform manual login"""
        if not auth_url:
            auth_url = f"https://ident.familysearch.org/cis-web/oauth2/v3/authorization?response_type=code&scope=openid profile email qualifies_for_affiliate_account country&client_id={self.client_id}&redirect_uri={self.redirect_uri}&username={self.username}"

        print("\n" + "=" * 60)
        print("Headless login failed. Manual login required.")
        print("=" * 60)
        print(f"Opening browser to login: {auth_url}")

        # Only open browser if we really are in a terminal context, but user asked to stop?
        # We will open it because otherwise they can't login.
        try:
            webbrowser.open(auth_url)
        except Exception:  # Catch specific exception
            pass

        print("\n" + "-" * 30)
        print("MANUAL FALLBACK:")
        print("1. Log in to FamilySearch in the opened window.")
        print("2. Once logged in, you will be redirected.")
        print(
            "3. Copy the 'code' from the URL or simply copy the FULL destination URL."
        )
        print(
            "   (If it says 'code already used', assume you need to re-login or check for Access Token)"
        )
        print("-" * 30)

        while True:
            try:
                user_input = getpass.getpass(
                    "Paste the code, token, or full redirect URL here: "
                ).strip()
                if not user_input:
                    sys.exit(2)

                code = None
                session_id = None

                # Check for Access Token first
                if "access_token=" in user_input:
                    try:
                        parsed = urlparse(user_input)
                        if parsed.fragment:
                            qs = parse_qs(parsed.fragment)
                            if "access_token" in qs:
                                session_id = qs["access_token"][0]
                        if not session_id and parsed.query:
                            qs = parse_qs(parsed.query)
                            if "access_token" in qs:
                                session_id = qs["access_token"][0]
                    except Exception:  # Catch specific exception
                        pass

                if (
                    not session_id
                    and len(user_input) > 50
                    and "=" not in user_input
                    and "http" not in user_input
                ):
                    session_id = user_input

                if session_id:
                    with self.lock:
                        self.headers.update({"Authorization": f"Bearer {session_id}"})
                        self.cookies.set(
                            "fssessionid", session_id, domain=".familysearch.org"
                        )
                    self.set_current(auto_login=False)
                    if self.logged and self.fid:
                        self.save_cookies()
                        print("\nSuccess! Session established via Token.")
                        return True

                    print("\nToken appeared invalid. Try again.")
                    continue

                # Check for Code
                if "code=" in user_input:
                    try:
                        parsed = urlparse(user_input)
                        qs = parse_qs(parsed.query)
                        if "code" in qs:
                            code = qs["code"][0]
                    except Exception:  # Catch specific exception
                        pass
                elif len(user_input) < 50:
                    code = user_input

                if code:
                    url = "https://ident.familysearch.org/cis-web/oauth2/v3/token"
                    try:
                        # Raw request to avoid cache
                        res = requests.post(
                            url,
                            data={
                                "grant_type": "authorization_code",
                                "client_id": self.client_id,
                                "code": code,
                                "redirect_uri": self.redirect_uri,
                            },
                            headers=self.headers,
                            timeout=self.timeout,
                        )

                        data = res.json()
                        if "access_token" in data:
                            session_id = data["access_token"]
                            with self.lock:
                                self.headers.update(
                                    {"Authorization": f"Bearer {session_id}"}
                                )
                                self.cookies.set(
                                    "fssessionid",
                                    session_id,
                                    domain=".familysearch.org",
                                )
                            self.set_current(auto_login=False)
                            if self.logged and self.fid:
                                self.save_cookies()
                                print("\nSuccess! Session established via Code.")
                                return True

                        error_desc = data.get(
                            "error_description", data.get("error", "Unknown error")
                        )
                        print(f"\nToken exchange failed: {error_desc}")

                    except Exception as e:
                        print(f"\nError during token exchange: {e}")

                print("Invalid input or failed login. Please try again.")

            except (EOFError, KeyboardInterrupt):
                print("\nLogin cancelled.")
                sys.exit(2)

    def get_url(self, url, headers=None, auto_login=True, no_api=False):
        """retrieve JSON structure from a FamilySearch URL"""
        self.counter += 1
        if headers is None:
            headers = {"Accept": "application/x-gedcomx-v1+json"}
        # headers.update(self.headers) - redundant, requests merges session headers automatically
        while True:
            try:
                self.write_log("Downloading: " + url)
                # Used HEAD logic here (explicit API URL)
                full_url = url if no_api else "https://api.familysearch.org" + url
                r = self.get(
                    full_url,
                    timeout=self.timeout,
                    headers=headers,
                )
            except requests.exceptions.ReadTimeout:
                self.write_log("Read timed out", level="warning")
                continue
            except requests.exceptions.ConnectionError:
                self.write_log("Connection aborted", level="warning")
                time.sleep(self.timeout)
                continue
            except sqlite3.InterfaceError as e:
                # Cache corruption from threading - log and retry without cache
                self.write_log(
                    "Cache error (sqlite3.InterfaceError): %s - Retrying without cache"
                    % e,
                    level="warning",
                )
                with self.cache_disabled():  # type: ignore[attr-defined]
                    try:
                        r = self.get(
                            full_url,
                            timeout=self.timeout,
                            headers=headers,
                        )
                    except requests.exceptions.RequestException as retry_err:
                        self.write_log(
                            "Retry blocked by network error: %s" % retry_err,
                            level="warning",
                        )
                        # Let the outer loop retry or fail gracefully
                        continue
            # Color status codes based on severity
            if r.status_code >= 500:
                self.write_log("Status code: %s" % r.status_code, level="error")
            elif r.status_code >= 400:
                self.write_log("Status code: %s" % r.status_code, level="warning")
            else:
                self.write_log("Status code: %s" % r.status_code)
            if self.verbose and hasattr(r, "from_cache") and r.from_cache:
                self.write_log("CACHE HIT: " + url)
            if r.status_code == 204:
                return None
            if r.status_code in {404, 405, 410, 500, 503, 504}:
                self.write_log("WARNING: " + url, level="warning")
                return None
            if r.status_code == 401:
                if auto_login:
                    self.login()
                    continue

                return None
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                self.write_log("HTTPError", level="error")
                # Log full request/response details for all HTTP errors
                self.write_log(
                    "  Request: GET https://api.familysearch.org%s" % url,
                    level="warning",
                )
                self.write_log(
                    (
                        "  Response: %s" % r.text[:500]
                        if len(r.text) > 500
                        else "  Response: %s" % r.text
                    ),
                    level="warning",
                )
                if r.status_code == 403:
                    try:
                        error_data = r.json()
                        if (
                            "errors" in error_data
                            and error_data["errors"]
                            and error_data["errors"][0].get("message")
                            == "Unable to get ordinances."
                        ):
                            self.write_log(
                                "Unable to get ordinances. "
                                "Try with an LDS account or without option -c.",
                                level="error",
                            )
                            return "error"
                        error_msg = error_data["errors"][0].get("message", "")
                        self.write_log(
                            "WARNING: code 403 from %s %s" % (url, error_msg),
                            level="warning",
                        )
                    except (ValueError, KeyError, IndexError):
                        self.write_log(
                            "WARNING: code 403 from %s (no error details)" % url,
                            level="warning",
                        )
                    return None
                time.sleep(self.timeout)
                continue
            try:
                return r.json()
            except Exception as e:
                self.write_log(
                    "WARNING: corrupted file from %s, error: %s" % (url, e),
                    level="warning",
                )

                return None

    def set_current(self, auto_login=True):
        """retrieve FamilySearch current user ID, name and language"""
        url = "/platform/users/current"
        data = self.get_url(url, auto_login=auto_login)
        if data:
            self.fid = data["users"][0]["personId"]
            self.lang = data["users"][0]["preferredLanguage"]
            self.display_name = data["users"][0]["displayName"]

    def _(self, string):
        """translate a string into user's language"""
        if self.lang and string in translations and self.lang in translations[string]:
            return translations[string][self.lang]
        return string


class CachedSession(GMASession, CSession):
    # pylint: disable=abstract-method
    def __init__(
        self,
        username,
        password,
        client_id=None,
        redirect_uri=None,
        verbose=False,
        logfile=False,
        timeout=60,
        cache_control=True,
        requests_per_second=5,
    ):
        # Cache setup - use ~/.cache/getmyancestors/ by default
        cache_dir = os.environ.get(
            "GMA_CACHE_DIR", os.path.expanduser("~/.cache/getmyancestors")
        )
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "requests")

        GMASession.__init__(
            self,
            username,
            password,
            client_id,
            redirect_uri,
            verbose=verbose,
            logfile=logfile,
            timeout=timeout,
            requests_per_second=requests_per_second,
        )

        # Offline mode adjustments
        offline_mode = bool(os.environ.get("GMA_OFFLINE_MODE"))
        expire_after = -1 if offline_mode else 86400

        # Use Filesystem backend as per requirement
        CSession.__init__(
            self,
            cache_path,
            backend="filesystem",
            expire_after=expire_after,
            allowable_codes=(200, 204),
            cache_control=cache_control,  # Enable HTTP conditional requests (ETag/Last-Modified)
            allow_to_fetch_missing=(not offline_mode),  # prevent fetch on miss
        )
        # Re-apply default headers as CSession.__init__ might have wiped them
        with self.lock:
            self.headers.update(self.DEFAULT_HEADERS)
        # Check for offline mode via environment variable
        if os.environ.get("GMA_OFFLINE_MODE"):
            self.write_log(
                "🔧 OFFLINE MODE ENABLED - skipping login and using cached data only."
            )
            # In offline mode, skip login - all requests must come from cache
            # Satisfaction for self.logged property
            with self.lock:
                self.headers.update({"Authorization": "Bearer OFFLINE"})
            self.fid = "OFFLINE"
            self.lang = "en"
            self.display_name = "Offline Mode"
        else:
            self.login()

    def request(self, *args, **kwargs):
        """Override request to block network in offline mode"""
        if os.environ.get("GMA_OFFLINE_MODE"):
            # Set only_if_cached to True for requests-cache
            kwargs["only_if_cached"] = True
        return super().request(*args, **kwargs)


class Session(GMASession):
    def __init__(
        self,
        username,
        password,
        client_id=None,
        redirect_uri=None,
        verbose=False,
        logfile=False,
        timeout=60,
        # pylint: disable=unused-argument
        cache_control=True,  # Ignored for non-cached sessions
        requests_per_second=5,
    ):
        GMASession.__init__(
            self,
            username,
            password,
            client_id,
            redirect_uri,
            verbose=verbose,
            logfile=logfile,
            timeout=timeout,
            requests_per_second=requests_per_second,
        )
        self.login()
