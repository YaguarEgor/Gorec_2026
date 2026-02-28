from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
import os


class Settings(BaseSettings):
    bot_token: SecretStr
    pg_link: SecretStr
    admin_password: SecretStr
    admin: SecretStr
    bot_token = os.getenv('BOT_TOKEN')
    pg_link = os.getenv('PG_LINK')
    admin_password = os.getenv('ADMIN_PASSWORD')
    admin = os.getenv('ADMIN')
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')


config = Settings()
