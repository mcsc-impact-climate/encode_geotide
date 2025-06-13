import os
from pathlib import Path

def get_top_dir():
    """
    Gets the path to the top level of the git repo (one level up from the source directory)

    Parameters
    ----------
    None

    Returns
    -------
    top_dir (string): Path to the top level of the git repo
    """
    source_path = Path(__file__).resolve()
    source_dir = source_path.parent
    top_dir = os.path.dirname(source_dir)
    return top_dir

def ensure_directory_exists(directory_path):
    """
    Checks if the specified directory exists, and if not, creates it.

    Parameters
    ----------
    directory_path (str): The path of the directory to check or create.

    Returns
    -------
    top_dir (string): Path to the top level of the git repo
    """
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)
        print(f"Directory '{directory_path}' created.")
    else:
        print(f"Directory '{directory_path}' already exists.")
