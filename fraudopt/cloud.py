"""Optional persistent SQLite across ephemeral GitHub Actions runners via Azure Blob."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path


def sync(direction: str, data_dir: Path) -> None:
    if direction not in {"pull", "push"}:
        raise ValueError("direction must be pull or push")
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if not connection_string:
        print("Azure not configured: job artefacts work, but SQLite history will not persist between hosted runs.")
        return
    from azure.storage.blob import BlobServiceClient
    from azure.core.exceptions import ResourceNotFoundError
    client = BlobServiceClient.from_connection_string(connection_string)
    container = os.getenv("AZURE_STORAGE_CONTAINER", "fraudopt-data")
    blob = client.get_blob_client(container=container, blob="complaints.sqlite")
    dest = data_dir / "complaints.sqlite"
    data_dir.mkdir(parents=True, exist_ok=True)
    if direction == "pull":
        try:
            restore_database(blob.download_blob().readall(), dest)
            print("Restored persistent complaints.sqlite from Azure Blob")
        except ResourceNotFoundError:
            print("No existing complaint store on Azure Blob; starting fresh")
    else:
        if not dest.exists():
            raise FileNotFoundError(dest)
        blob.upload_blob(dest.read_bytes(), overwrite=True)
        print("Updated persistent complaints.sqlite on Azure Blob")


def restore_database(payload: bytes, dest: Path) -> None:
    """Validate a staged download before replacing a working store."""
    temp = dest.with_suffix(".restore")
    try:
        temp.write_bytes(payload)
        conn = sqlite3.connect(f"{temp.resolve().as_uri()}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("Downloaded SQLite database failed integrity check")
            conn.execute("SELECT complaint_id,date_received,product,issue,sub_issue,state,potential_fraud_issue FROM complaints LIMIT 0")
        finally:
            conn.close()
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)
