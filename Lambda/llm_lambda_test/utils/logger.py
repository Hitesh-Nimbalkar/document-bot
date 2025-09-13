import logging
import sys
import traceback
import inspect
from typing import Optional

# -----------------------------
# Custom Logger
# -----------------------------
class CustomLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s "
                    "(%(filename)s:%(lineno)d - %(funcName)s): %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.logger.setLevel(logging.DEBUG)

    def _inject_classname(self, msg: str) -> str:
        """
        Detect class name if log call was made inside a class method.
        """
        frame = inspect.currentframe().f_back.f_back
        cls = None
        if "self" in frame.f_locals:
            cls = frame.f_locals["self"].__class__.__name__
        return f"[{cls}] {msg}" if cls else msg

    def debug(self, msg, *args, **kwargs):
        self.logger.debug(self._inject_classname(msg), *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.logger.info(self._inject_classname(msg), *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(self._inject_classname(msg), *args, **kwargs)

    def error(self, msg, *args, exc_info=False, **kwargs):
        self.logger.error(self._inject_classname(msg), *args, exc_info=exc_info, **kwargs)

    def critical(self, msg, *args, exc_info=False, **kwargs):
        self.logger.critical(self._inject_classname(msg), *args, exc_info=exc_info, **kwargs)


# -----------------------------
# Lambda-safe Custom Exception
# -----------------------------
class CustomException(Exception):
    def __init__(self, message: str, error_details: Optional[object] = None):
        norm_msg = str(message) if not isinstance(message, BaseException) else str(message)

        exc_type = exc_value = exc_tb = None
        if error_details is None:
            exc_type, exc_value, exc_tb = sys.exc_info()
        elif isinstance(error_details, BaseException):
            exc_type, exc_value, exc_tb = type(error_details), error_details, error_details.__traceback__
        else:
            exc_type, exc_value, exc_tb = sys.exc_info()

        # Traverse traceback to last frame
        last_tb = exc_tb
        while last_tb and last_tb.tb_next:
            last_tb = last_tb.tb_next

        self.file_name = last_tb.tb_frame.f_code.co_filename if last_tb else "<unknown>"
        self.func_name = last_tb.tb_frame.f_code.co_name if last_tb else "<unknown>"
        self.lineno = last_tb.tb_lineno if last_tb else -1
        self.message = norm_msg

        # Full traceback string
        self.traceback_str = ''.join(
            traceback.format_exception(exc_type, exc_value, exc_tb)
        ) if exc_type and exc_tb else ""

        super().__init__(self.__str__())

    def __str__(self):
        base = f"Error in [{self.file_name}:{self.lineno} - {self.func_name}] | Message: {self.message}"
        return f"{base}\nTraceback:\n{self.traceback_str}" if self.traceback_str else base

    def __repr__(self):
        return f"CustomException(file={self.file_name!r}, line={self.lineno}, message={self.message!r})"
