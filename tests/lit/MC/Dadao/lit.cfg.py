import lit.formats
import os

config.name = "DADAO MC tests"
config.test_format = lit.formats.ShTest()
config.suffixes = [".s"]
config.test_source_root = os.path.dirname(__file__)
config.test_exec_root = config.test_source_root

llvm_build_dir = getattr(config, "llvm_build_dir",
                         os.getenv("LLVM_BUILD_DIR",
                                   os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".work", "build", "llvm")))
tool_dirs = [os.path.join(llvm_build_dir, "bin")]
config.environment["PATH"] = ":".join(tool_dirs) + ":" + config.environment.get("PATH", "")
