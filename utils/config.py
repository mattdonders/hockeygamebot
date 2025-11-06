import yaml


def load_config(config_file: str):
    """
    Load configuration settings from a YAML file.

    This function reads and parses a YAML file to load configuration data into a
    Python dictionary. It ensures proper error handling for missing files or
    invalid YAML syntax.

    Args:
        config_file (str): The file path to the YAML configuration file.

    Returns:
        dict: A dictionary containing the parsed configuration data.

    Raises:
        FileNotFoundError: If the specified configuration file is not found.
        Exception: If there is an error while parsing the YAML file.

    Example Usage:
        config = load_config("config.yaml")
        print(config["team_name"])  # Access specific configuration values.

    Notes:
        - The function uses `yaml.safe_load` to safely parse the YAML file,
          which avoids executing arbitrary Python code.
        - Ensure the configuration file is properly formatted as YAML to
          prevent parsing errors.
    """
    try:
        with open(config_file) as file:
            config = yaml.safe_load(file)
            return config
    except FileNotFoundError:
        raise Exception(f"Configuration file {config_file} not found.")
    except yaml.YAMLError as e:
        raise Exception(f"Error parsing YAML file: {e}")
