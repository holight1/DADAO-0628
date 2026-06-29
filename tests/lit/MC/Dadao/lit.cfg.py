import lit.formats
import os

config.name = "DADAO MC tests"
config.test_format = lit.formats.ShTest()
config.suffixes = [".s"]
config.test_source_root = os.path.dirname(__file__)
config.test_exec_root = config.test_source_root

tool_dirs = [os.path.join(config.llvm_build_dir, "bin")]
config.environment["PATH"] = ":".join(tool_dirs) + ":" + config.environment.get("PATH", "")
