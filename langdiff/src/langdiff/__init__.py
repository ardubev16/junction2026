def main() -> None:
    import uvicorn

    uvicorn.run("langdiff.app:app", host="127.0.0.1", port=8000)


def load() -> None:
    from .load import main as load_main

    load_main()
