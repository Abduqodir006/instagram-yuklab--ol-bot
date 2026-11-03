"""aiogram o'rnatilmagan muhitda (masalan, sandbox) handler/sender mantig'ini
sinash uchun minimal stub. Haqiqiy aiogram bo'lsa ISHLATILMAYDI.
Stub aiogram API'sining to'g'riligini tekshirmaydi - faqat bizning mantiqni."""
import sys
import types


def install_if_missing() -> bool:
    try:
        import aiogram  # noqa: F401
        return False
    except ImportError:
        pass

    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    class TelegramAPIError(Exception):
        def __init__(self, method=None, message=""):
            super().__init__(message)
            self.method, self.message = method, message

        def __str__(self):
            return self.message

    class TelegramNetworkError(TelegramAPIError):
        pass

    class TelegramRetryAfter(TelegramAPIError):
        def __init__(self, method=None, message="", retry_after=1):
            super().__init__(method, message)
            self.retry_after = retry_after

    class TelegramBadRequest(TelegramAPIError):
        pass

    class TelegramForbiddenError(TelegramAPIError):
        pass

    class _Any:
        def __getattr__(self, _):
            return self

        def __call__(self, *a, **k):
            return self

    class Router:
        def __init__(self, *a, **k):
            pass

        def message(self, *a, **k):
            return lambda f: f

        def include_router(self, r):
            pass

    class Dispatcher(Router):
        def __init__(self, *a, **k):
            self.workflow_data = {}

    class Command:
        def __init__(self, *a, **k):
            pass

    class CommandObject:
        def __init__(self, args=None):
            self.args = args

    class CommandStart(Command):
        pass

    class FSInputFile:
        def __init__(self, path, filename=None, chunk_size=65536):
            self.path, self.filename = path, filename

    class Bot:
        pass

    class Message:
        pass

    class DefaultBotProperties:
        def __init__(self, **k):
            pass

    class ParseMode:
        HTML = "HTML"

    class ChatAction:
        UPLOAD_VIDEO = "upload_video"

    mod("aiogram", Bot=Bot, Dispatcher=Dispatcher, Router=Router, F=_Any())
    mod("aiogram.filters", Command=Command, CommandStart=CommandStart, CommandObject=CommandObject)
    mod("aiogram.types", Message=Message, FSInputFile=FSInputFile)
    mod("aiogram.enums", ParseMode=ParseMode, ChatAction=ChatAction)
    mod("aiogram.client")
    mod("aiogram.client.default", DefaultBotProperties=DefaultBotProperties)
    mod(
        "aiogram.exceptions",
        TelegramAPIError=TelegramAPIError, TelegramNetworkError=TelegramNetworkError,
        TelegramRetryAfter=TelegramRetryAfter, TelegramBadRequest=TelegramBadRequest,
        TelegramForbiddenError=TelegramForbiddenError,
    )
    return True
