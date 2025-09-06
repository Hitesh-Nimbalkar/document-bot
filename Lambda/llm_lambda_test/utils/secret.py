
import os
import boto3
from botocore.exceptions import ClientError
def get_secret(secret_env_var):
    """
    Fetches a secret value from AWS Secrets Manager using the secret name from an environment variable.
    :param secret_env_var: The environment variable name that holds the secret name
    :return: The secret value as a string, or None if not found
    """
    secret_name = os.environ.get(secret_env_var)
    if not secret_name:
        raise ValueError(f"Environment variable '{secret_env_var}' not set.")
    client = boto3.client('secretsmanager')
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        return get_secret_value_response["SecretString"]
    except ClientError as e:
        print(f"Unable to fetch secret '{secret_name}' from Secrets Manager: {e}")
        return None
