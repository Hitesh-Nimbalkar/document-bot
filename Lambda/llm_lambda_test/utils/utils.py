

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
        Detect class name and enhanced module info if log call was made inside a class method.
        """
        frame = inspect.currentframe().f_back.f_back
        cls = None
        module_name = None
        file_path = None
        
        if frame:
            # Get class name if inside a class method
            if "self" in frame.f_locals:
                cls = frame.f_locals["self"].__class__.__name__
            
            # Get module information
            module_name = frame.f_globals.get('__name__', 'unknown_module')
            file_path = frame.f_code.co_filename
            
            # Extract just the filename for cleaner display
            filename = file_path.split('/')[-1] if file_path else 'unknown_file'
            
        # Build enhanced log prefix
        parts = []
        if module_name and module_name != 'unknown_module':
            parts.append(f"Module:{module_name}")
        if filename and filename != 'unknown_file':
            parts.append(f"File:{filename}")
        if cls:
            parts.append(f"Class:{cls}")
            
        prefix = f"[{' | '.join(parts)}]" if parts else "[Unknown]"
        return f"{prefix} {msg}"
    def debug(self, msg, *args, **kwargs):
        self.logger.debug(self._inject_classname(msg), *args, **kwargs)
    def info(self, msg, *args, **kwargs):
        self.logger.info(self._inject_classname(msg), *args, **kwargs)
    def warning(self, msg, *args, **kwargs):
        self.logger.warning(self._inject_classname(msg), *args, **kwargs)
    def error(self, msg, *args, exc_info=False, **kwargs):
        # Auto-detect import errors and enhance the message
        if exc_info or (args and isinstance(args[0], ImportError)):
            enhanced_msg = self._enhance_import_error_message(msg)
            self.logger.error(self._inject_classname(enhanced_msg), *args, exc_info=True, **kwargs)
        else:
            self.logger.error(self._inject_classname(msg), *args, exc_info=exc_info, **kwargs)
    def critical(self, msg, *args, exc_info=False, **kwargs):
        # Auto-detect import errors and enhance the message
        if exc_info or (args and isinstance(args[0], ImportError)):
            enhanced_msg = self._enhance_import_error_message(msg)
            self.logger.critical(self._inject_classname(enhanced_msg), *args, exc_info=True, **kwargs)
        else:
            self.logger.critical(self._inject_classname(msg), *args, exc_info=exc_info, **kwargs)
            
    def import_error(self, missing_module: str, attempted_from: str = None, fallback_info: str = None):
        """
        Specialized method for logging import errors with detailed context.
        
        Args:
            missing_module: The module that failed to import
            attempted_from: The module/file that tried to import it
            fallback_info: Information about any fallback being used
        """
        frame = inspect.currentframe().f_back
        caller_file = frame.f_code.co_filename.split('/')[-1] if frame else 'unknown_file'
        caller_module = frame.f_globals.get('__name__', 'unknown_module') if frame else 'unknown_module'
        caller_line = frame.f_lineno if frame else 'unknown_line'
        
        error_msg = f"❌ IMPORT ERROR: Cannot import '{missing_module}'"
        location_msg = f"📍 LOCATION: Module '{caller_module}' in file '{caller_file}' at line {caller_line}"
        
        if attempted_from:
            error_msg += f" (attempted from {attempted_from})"
            
        if fallback_info:
            fallback_msg = f"🔄 FALLBACK: {fallback_info}"
            self.logger.warning(f"{error_msg}\n{location_msg}\n{fallback_msg}")
        else:
            self.logger.error(f"{error_msg}\n{location_msg}")
    
    def _enhance_import_error_message(self, msg: str) -> str:
        """
        Enhance import error messages with detailed location and context.
        """
        frame = inspect.currentframe().f_back.f_back.f_back  # Go up the call stack
        if frame:
            file_path = frame.f_code.co_filename
            filename = file_path.split('/')[-1]
            module_name = frame.f_globals.get('__name__', 'unknown_module')
            line_no = frame.f_lineno
            func_name = frame.f_code.co_name
            
            # Check if it's an import error context
            if 'import' in msg.lower() or 'ImportError' in str(msg):
                enhanced = f"🚨 IMPORT ERROR DETECTED 🚨\n"
                enhanced += f"📁 File: {filename} (Full path: {file_path})\n"
                enhanced += f"📦 Module: {module_name}\n"
                enhanced += f"📍 Line: {line_no}\n"
                enhanced += f"🔧 Function: {func_name}\n"
                enhanced += f"💬 Original Message: {msg}"
                return enhanced
        
        return msg

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
logger = CustomLogger(__name__)
