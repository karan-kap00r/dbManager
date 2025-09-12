import os
import typer
from commands import app  # Typer app from commands.py

if __name__ == "__main__":
    os.makedirs("migrations", exist_ok=True)
    app()
