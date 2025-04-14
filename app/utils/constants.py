"""
    This module contains the constants for the application.
"""
from enum import Enum

class Permissions(str, Enum):
    """
    Enum class for all permissions.
    """
    VIEW_CHART = "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a2"
    CREATE_CHART = "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a3"
    CREATE_ROLE = "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a4"
    CREATE_USER = "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a5"
    VIEW_DASHBOARD = "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a6"
    CREATE_DASHBOARD = "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a7"
    DELETE_CHART = "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a9"
    DELETE_DASHBOARD = "6e073b1d-f56c-4a6e-8a9d-2cb37a4702b4"
    CREATE_PROJECT = "8e1c6f1e-7c99-4f28-bd2e-c7b79d6122c1"
    ADD_DATASOURCE = "f11a63e3-fc6e-4d36-aeae-943d118c3e27"
    VIEW_DATASOURCE = "6e073b1d-f56c-4a6e-8a9d-2cb37a470393"
    ADD_USER_DASHBOARD ="f89c88c2-64a1-4c73-9a71-72cf02e6f2f0"
    EDIT_PROJECT = "6e073b1d-f56c-4a6e-8a9d-2cb37a4703a8"
    DELETE_PROJECT = "f89c88c2-64a1-4c73-9a71-72cf02e6f2f1"
    EDIT_DASHBOARD = "0a4d0f7e-3ae5-4c13-9cc4-dc7e487cdb48"
    EDIT_ROLE = "0a4d0f7e-3ae5-4c13-9cc4-dc7e487cdb49"
    DELETE_ROLE = "3f62d2c3-58ff-402f-bf1a-b199a43f607e"
    EDIT_USER ="0a4d0f7e-3ae5-4c13-9cc4-dc7e487cdb50"
    DELETE_USER ="0a4d0f7e-3ae5-4c13-9cc4-dc7e487cdb51"
    EDIT_DATASOURCE = "0a4d0f7e-3ae5-4c13-9cc4-dc7e487cdb52"
    DELETE_DATASOURCE = "0a4d0f7e-3ae5-4c13-9cc4-dc7e487cdb53"

POOL_RECYCLE = 300
POOL_SIZE = 5
MAX_OVERFLOW = 0

ALLOWED_ORIGINS=["http://localhost:3000"]
ALLOWED_CREDENTIALS = True
ALLOWED_METHODS = ["*"]
ALLOWED_HEADERS = ["*"]
