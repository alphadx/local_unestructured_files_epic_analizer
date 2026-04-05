from __future__ import annotations

import importlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import ScanRequest, SourceProvider

logger = logging.getLogger(__name__)


def _get_google_drive_service(request: ScanRequest):
    try:
        google_auth = importlib.import_module("google.oauth2.service_account")
        googleapiclient = importlib.import_module("googleapiclient.discovery")
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Google Drive support requires google-auth and google-api-python-client. "
            "Install them via requirements or pip."
        ) from exc

    service_account_info = request.source_options.get(
        "service_account_json",
        settings.google_drive_service_account_json,
    )
    if not service_account_info:
        raise RuntimeError(
            "Google Drive service account credentials are required in source_options.service_account_json "
            "or GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON."
        )

    folder_id = request.source_options.get("folder_id") or settings.google_drive_folder_id or request.path
    if not folder_id:
        raise RuntimeError(
            "Google Drive folder ID is required in path, source_options.folder_id, or environment GOOGLE_DRIVE_FOLDER_ID."
        )

    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    credentials = google_auth.Credentials.from_service_account_info(
        service_account_info, scopes=scopes
    )
    return googleapiclient.build("drive", "v3", credentials=credentials, cache_discovery=False), folder_id


def _download_google_drive_file(service: Any, file_id: str, local_path: Path, mime_type: str | None) -> None:
    try:
        media_module = importlib.import_module("googleapiclient.http")
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Google Drive support requires google-api-python-client. Install it via requirements or pip."
        ) from exc

    MediaIoBaseDownload = getattr(media_module, "MediaIoBaseDownload")
    local_path.parent.mkdir(parents=True, exist_ok=True)

    if mime_type and mime_type.startswith("application/vnd.google-apps"):
        export_map = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "application/pdf",
        }
        export_type = export_map.get(mime_type)
        if export_type:
            request = service.files().export(fileId=file_id, mimeType=export_type)
            with open(local_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            return
        # Fall back to metadata-only placeholder for unsupported app formats
        local_path.write_text("[Google Drive file type not exported]", encoding="utf-8")
        return

    request = service.files().get_media(fileId=file_id)
    with open(local_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def _list_google_drive_folder(service: Any, folder_id: str) -> list[dict[str, Any]]:
    query = f"'{folder_id}' in parents and trashed=false"
    page_token = None
    results: list[dict[str, Any]] = []
    while True:
        response = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
                pageSize=1000,
            )
            .execute()
        )
        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return results


def _fetch_google_drive_folder(service: Any, folder_id: str, destination: Path) -> None:
    metadata = service.files().get(fileId=folder_id, fields="id, name, mimeType").execute()
    if metadata.get("mimeType") == "application/vnd.google-apps.folder":
        children = _list_google_drive_folder(service, folder_id)
        for child in children:
            child_name = child["name"]
            child_id = child["id"]
            child_type = child.get("mimeType")
            child_path = destination / child_name
            if child_type == "application/vnd.google-apps.folder":
                _fetch_google_drive_folder(service, child_id, child_path)
            else:
                _download_google_drive_file(service, child_id, child_path, child_type)
    else:
        _download_google_drive_file(service, folder_id, destination / metadata["name"], metadata.get("mimeType"))


def _get_graph_access_token() -> str:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "SharePoint support requires the requests package. Install it via requirements or pip."
        ) from exc

    tenant_id = settings.sharepoint_tenant_id
    client_id = settings.sharepoint_client_id
    client_secret = settings.sharepoint_client_secret
    if not tenant_id or not client_id or not client_secret:
        raise RuntimeError(
            "SharePoint tenant and client credentials are required in environment variables."
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    response = requests.post(
        token_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Failed to obtain SharePoint access token")
    return token


def _graph_get_children(token: str, url: str) -> list[dict[str, Any]]:
    import requests

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json().get("value", [])


def _download_sharepoint_file(token: str, download_url: str, destination: Path) -> None:
    import requests

    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(download_url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    response.raise_for_status()
    destination.write_bytes(response.content)


def _fetch_sharepoint_folder(
    token: str,
    base_url: str,
    drive_id: str,
    destination: Path,
) -> None:
    children = _graph_get_children(token, f"{base_url}/children")
    for item in children:
        item_name = item.get("name")
        if not item_name:
            continue
        item_path = destination / item_name
        if item.get("folder") is not None:
            _fetch_sharepoint_folder(
                token,
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item['id']}",
                drive_id,
                item_path,
            )
        elif item.get("file") is not None:
            download_url = item.get("@microsoft.graph.downloadUrl")
            if not download_url:
                continue
            _download_sharepoint_file(token, download_url, item_path)


def _build_sharepoint_root_url(request: ScanRequest) -> str:
    site_id = request.source_options.get("site_id") or settings.sharepoint_site_id
    drive_id = request.source_options.get("drive_id") or settings.sharepoint_drive_id
    path = request.path.strip("/")
    if not site_id or not drive_id:
        raise RuntimeError(
            "SharePoint source requires site_id and drive_id in source_options or environment settings."
        )
    if path:
        return f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{path}:"
    return f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root"


def _rewrite_paths(file_indices: list[Any], root_path: str, remote_prefix: str) -> list[Any]:
    rewritten: list[Any] = []
    for fi in file_indices:
        if fi.path.startswith(root_path):
            relative = os.path.relpath(fi.path, root_path)
            fi.path = f"{remote_prefix}/{relative}" if relative != "." else remote_prefix
        rewritten.append(fi)
    return rewritten


def prepare_scan_source(request: ScanRequest) -> tuple[str, bool]:
    if request.source_provider == SourceProvider.LOCAL:
        return request.path, False

    temp_dir = tempfile.mkdtemp(prefix="remote_source_")
    destination = Path(temp_dir)
    logger.info("Preparing remote source %s into %s", request.source_provider, temp_dir)

    if request.source_provider == SourceProvider.GOOGLE_DRIVE:
        service, folder_id = _get_google_drive_service(request)
        _fetch_google_drive_folder(service, folder_id, destination)
        remote_prefix = f"googledrive://{folder_id}"
    elif request.source_provider == SourceProvider.SHAREPOINT:
        token = _get_graph_access_token()
        root_url = _build_sharepoint_root_url(request)
        drive_id = request.source_options.get("drive_id") or settings.sharepoint_drive_id
        _fetch_sharepoint_folder(token, root_url, drive_id, destination)
        site_id = request.source_options.get("site_id") or settings.sharepoint_site_id
        remote_prefix = f"sharepoint://{site_id}/{drive_id}"
    else:
        raise RuntimeError(f"Unsupported source provider: {request.source_provider}")

    request.source_options["_remote_prefix"] = remote_prefix
    return temp_dir, True


def rewrite_remote_paths(
    file_indices: list[Any], root_path: str, remote_prefix: str
) -> list[Any]:
    return _rewrite_paths(file_indices, root_path, remote_prefix)


def cleanup_source_path(path: str) -> None:
    try:
        import shutil

        shutil.rmtree(path)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to cleanup temporary remote source path %s: %s", path, exc)
