from aiogram import Dispatcher

from bot.handlers import export, generate, start, status


def register_all(dp: Dispatcher) -> None:
    dp.include_routers(
        start.router,
        generate.router,
        export.router,
        status.router,
    )
