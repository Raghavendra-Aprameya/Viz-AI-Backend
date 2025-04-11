from enum import Enum

class Permissions(str, Enum):
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
