from gpubench import cli


def test_parser_has_subcommands():
    parser = cli.build_parser()
    args = parser.parse_args(["info", "--device", "cpu"])
    assert args.command == "info"
    assert args.device == "cpu"


def test_quick_flag_parses():
    parser = cli.build_parser()
    args = parser.parse_args(["all", "--quick"])
    assert args.quick is True
