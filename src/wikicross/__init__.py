def main() -> None:
    import uvicorn

    uvicorn.run("wikicross.app:app", host="127.0.0.1", port=8000)
