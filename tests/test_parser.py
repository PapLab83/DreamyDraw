from src.utils.cli_parser import parse_count

def test_parse_count_numeric():
    assert parse_count("сделай 5 лисиц") == 5
    assert parse_count("3 картинки") == 3

def test_parse_count_default():
    assert parse_count("просто лиса") == 3

def test_parse_count_large():
    assert parse_count("хочу 100 сказок") == 100
