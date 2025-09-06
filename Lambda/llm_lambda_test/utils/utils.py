import logging
import structlog
import sys
import traceback
from typing import Optional, cast

# -----------------------------
# Lambda-safe Custom Logger
# -----------------------------
class CustomLogger:
    def __init__(self, name: str = __file__):
        self.logger_name = name

        # Console handler for CloudWatch
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(message)s"))

        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            handlers=[console_handler]
        )

        # Structlog JSON configuration
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
                structlog.processors.add_log_level,
                structlog.processors.EventRenamer(to="event"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        self.logger = structlog.get_logger(self.logger_name)

    def info(self, msg: str):
        self.logger.info(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(msg)

    def debug(self, msg: str):
        self.logger.debug(msg)


# -----------------------------
# Lambda-safe Custom Exception
# -----------------------------
class CustomException(Exception):
    def __init__(self, message: str, error_details: Optional[object] = None):
        # Normalize message
        norm_msg = str(message) if not isinstance(message, BaseException) else str(message)

        # Capture traceback
        exc_type = exc_value = exc_tb = None
        if error_details is None:
            exc_type, exc_value, exc_tb = sys.exc_info()
        elif isinstance(error_details, BaseException):
            exc_type, exc_value, exc_tb = type(error_details), error_details, error_details.__traceback__
        else:
            exc_type, exc_value, exc_tb = sys.exc_info()

        # Get last frame info
        last_tb = exc_tb
        while last_tb and last_tb.tb_next:
            last_tb = last_tb.tb_next

        self.file_name = last_tb.tb_frame.f_code.co_filename if last_tb else "<unknown>"
        self.lineno = last_tb.tb_lineno if last_tb else -1
        self.message = norm_msg

        # Full traceback string
        self.traceback_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb)) if exc_type and exc_tb else ""

        super().__init__(self.__str__())

    def __str__(self):
        base = f"Error in [{self.file_name}] at line [{self.lineno}] | Message: {self.message}"
        return f"{base}\nTraceback:\n{self.traceback_str}" if self.traceback_str else base

    def __repr__(self):
        return f"CustomException(file={self.file_name!r}, line={self.lineno}, message={self.message!r})"
