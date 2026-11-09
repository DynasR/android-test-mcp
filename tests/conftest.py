import pytest

from android_test_mcp.policy import Policy
from android_test_mcp.server import build_server

from fakes import DEMO, FakeDevice, FakeWorld, make_apk
from helpers import FAST, PHYSICAL


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def world():
    """One emulator and one physical phone, both attached."""
    return FakeWorld({"emulator-5554": FakeDevice(),
                      PHYSICAL: FakeDevice(model="SM-G991B", qemu=False)})


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "demo_app"
    (root / "integration_test").mkdir(parents=True)
    (root / "pubspec.yaml").write_text("name: demo_app\n")
    (root / "integration_test" / "app_test.dart").write_text("void main() {}\n")
    (root / "README.md").write_text("not a test\n")
    return root


@pytest.fixture
def apk(tmp_path):
    return make_apk(tmp_path / "app-debug.apk", DEMO)


@pytest.fixture
def evidence_dir(tmp_path):
    return tmp_path / "evidence"


@pytest.fixture
def make_server(world, project, evidence_dir):
    def make(packages=(DEMO,), projects=None, devices=()):
        policy = Policy.create(packages, [project] if projects is None else projects, devices)
        return build_server(policy, evidence_dir, runner=world, timing=FAST)
    return make
