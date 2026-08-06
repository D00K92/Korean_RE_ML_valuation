import argparse
import os
from typing import List, Optional
from google.cloud import storage


class GCSDataFetcher:
    """Modular helper class to download datasets from Google Cloud Storage to local disk."""

    def __init__(self, bucket_name: str, project_id: Optional[str] = None):
        """
        Initialize the GCS client.
        
        Args:
            bucket_name: Name of the target GCS bucket.
            project_id: Optional GCP project ID (uses default ADC if None).
        """
        self.bucket_name = bucket_name
        self.client = storage.Client(project=project_id)
        self.bucket = self.client.bucket(bucket_name)

    def download_file(self, gcs_blob_path: str, local_destination_path: str) -> str:
        """Downloads a single blob file from GCS.

        Args:
            gcs_blob_path: Path to blob in GCS (e.g., 'raw/trades.parquet').
            local_destination_path: Local destination file path.

        Returns:
            The local file path where data was written.
        """
        blob = self.bucket.blob(gcs_blob_path)

        # Create local parent directories if they don't exist
        os.makedirs(os.path.dirname(local_destination_path), exist_ok=True)

        print(f"Downloading gs://{self.bucket_name}/{gcs_blob_path} -> {local_destination_path}")
        blob.download_to_filename(local_destination_path)
        print("Download completed successfully.")
        return local_destination_path

    def download_prefix(self, gcs_prefix: str, local_dir: str) -> List[str]:
        """Downloads all files matching a specific folder/prefix from GCS.

        Args:
            gcs_prefix: Folder prefix in GCS (e.g., 'raw/historical_trades/').
            local_dir: Target local directory.

        Returns:
            List of downloaded local file paths.
        """
        blobs = self.client.list_blobs(self.bucket_name, prefix=gcs_prefix)
        downloaded_files = []

        for blob in blobs:
            # Skip virtual directory marker blobs ending in '/'
            if blob.name.endswith('/'):
                continue

            # Preserve GCS folder sub-structure locally
            relative_path = os.path.relpath(blob.name, start=gcs_prefix)
            local_file_path = os.path.join(local_dir, relative_path)

            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            print(f"Downloading: gs://{self.bucket_name}/{blob.name} -> {local_file_path}")
            blob.download_to_filename(local_file_path)
            downloaded_files.append(local_file_path)

        print(f"Successfully downloaded {len(downloaded_files)} files to '{local_dir}'.")
        return downloaded_files


# CLI Execution Entrypoint
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch datasets from GCS to local environment.")
    parser.add_argument("--bucket", type=str, required=True, help="GCS Bucket Name")
    parser.add_argument("--gcs-path", type=str, required=True, help="GCS blob path or directory prefix")
    parser.add_argument("--local-dir", type=str, default="./data/raw", help="Local target directory")
    parser.add_argument("--project", type=str, default=None, help="GCP Project ID")

    args = parser.parse_args()

    fetcher = GCSDataFetcher(bucket_name=args.bucket, project_id=args.project)

    # If gcs-path looks like a single file
    if args.gcs_path.endswith(".parquet") or args.gcs_path.endswith(".csv"):
        filename = os.path.basename(args.gcs_path)
        local_target = os.path.join(args.local_dir, filename)
        fetcher.download_file(gcs_blob_path=args.gcs_path, local_destination_path=local_target)
    else:
        # Treat as prefix/directory
        fetcher.download_prefix(gcs_prefix=args.gcs_path, local_dir=args.local_dir)