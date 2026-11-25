import pytest

from mcp_status_page.providers import aws
from mcp_status_page.registry import ConfigError, load_registry, resolve, suggest


def test_builtins_load():
    services = load_registry()
    assert {"github", "aws", "azure", "gcp", "slack", "openai", "cloudflare"} <= services.keys()
    assert services["aws"].url == aws.PAGE
    assert services["openai"].provider == "incidentio"
    assert services["github"].url == "https://www.githubstatus.com"


def test_builtin_domains_do_not_overlap():
    seen: dict[str, str] = {}
    for service in load_registry().values():
        for domain in service.domains:
            assert domain not in seen, f"{domain} in both {seen[domain]} and {service.key}"
            seen[domain] = service.key


def test_resolve_by_key_alias_domain_and_url():
    services = load_registry()
    assert resolve(services, "GitHub").key == "github"
    assert resolve(services, "gh").key == "github"
    assert resolve(services, "api.github.com").key == "github"
    assert resolve(services, "https://api.github.com/repos/a/b").key == "github"
    assert resolve(services, "s3.us-east-1.amazonaws.com").key == "aws"
    assert resolve(services, "registry.npmjs.org:443").key == "npm"
    assert resolve(services, "notgithub.com") is None
    assert resolve(services, "nope") is None


def test_suggest_close_names():
    assert suggest(load_registry(), "githb")[0] == "github"


def test_user_config_adds_and_overrides(tmp_path):
    cfg = tmp_path / "services.toml"
    cfg.write_text(
        """
[services.myco]
provider = "statuspage"
url = "https://status.myco.com/"
domains = ["API.myco.com"]

[services.github]
provider = "statuspage"
url = "https://github-mirror.example.com"
"""
    )
    services = load_registry(cfg)
    assert services["myco"].url == "https://status.myco.com"
    assert services["myco"].name == "myco"
    assert resolve(services, "api.myco.com").key == "myco"
    assert services["github"].url == "https://github-mirror.example.com"
    assert services["github"].domains == []  # override replaces the whole entry
    assert "aws" in services


def test_fixed_provider_ignores_url(tmp_path):
    cfg = tmp_path / "services.toml"
    cfg.write_text('[services.cloud]\nprovider = "aws"\nurl = "https://elsewhere.example"\n')
    assert load_registry(cfg)["cloud"].url == aws.PAGE


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('[services.x]\nprovider = "nope"\nurl = "https://a.b"', "services.x.provider: expected one of"),
        ('[services.x]\nprovider = "statuspage"', "services.x.url: expected an http(s) URL"),
        ('[services.x]\nprovider = "statuspage"\nurl = "ftp://a.b"', "services.x.url: expected an http(s) URL"),
        ('[services.x]\nprovider = "statuspage"\nurl = "https://a.b"\ndomains = "a.b"', "services.x.domains: expected a list of strings"),
        ('[services.x]\nprovider = "statuspage"\nurl = "https://a.b"\nname = 3', "services.x.name: expected a string"),
        ("services = 1", "'services' must be a table"),
        ("services.x = 1", "services.x: must be a table"),
        ("[services", "invalid TOML"),
        ('[services.x]\nprovider = ["statuspage"]\nurl = "https://a.b"', "services.x.provider: expected one of"),
        ('[services.x]\nprovider = "statuspage"\nurl = "http://[abc"', "services.x.url: expected an http(s) URL"),
        ('[services.x]\nprovider = "statuspage"\nurl = "https://a.b"\naliases = [1]', "services.x.aliases: expected a list of strings"),
    ],
)
def test_config_errors_name_file_and_field(tmp_path, body, message):
    cfg = tmp_path / "bad.toml"
    cfg.write_text(body)
    with pytest.raises(ConfigError) as exc:
        load_registry(cfg)
    assert message in str(exc.value)
    assert str(cfg) in str(exc.value)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="cannot read file"):
        load_registry(tmp_path / "absent.toml")


def test_non_utf8_config_file(tmp_path):
    cfg = tmp_path / "bad.toml"
    cfg.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ConfigError, match="not UTF-8 text"):
        load_registry(cfg)


def test_resolve_malformed_url_returns_none():
    assert resolve(load_registry(), "http://[::1") is None
