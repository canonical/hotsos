from functools import partial

import pytest
from unittest import mock
from charms.layer import kubernetes_common


class TestCreateKubeConfig:
    @pytest.fixture(autouse=True)
    def _files(self, tmp_path):
        self.cfg_file = tmp_path / "config"
        self.ca_file = tmp_path / "ca.crt"
        self.ca_file.write_text("foo")
        self.ckc = partial(
            kubernetes_common.create_kubeconfig,
            self.cfg_file,
            "server",
            self.ca_file,
        )

    def test_guard_clauses(self):
        with pytest.raises(ValueError):
            self.ckc()
        assert not self.cfg_file.exists()
        with pytest.raises(ValueError):
            self.ckc(token="token", password="password")
        assert not self.cfg_file.exists()
        with pytest.raises(ValueError):
            self.ckc(key="key")
        assert not self.cfg_file.exists()

    def test_file_creation(self):
        self.ckc(password="password")
        assert self.cfg_file.exists()
        cfg_data_1 = self.cfg_file.read_text()
        assert cfg_data_1

    def test_idempotency(self):
        self.ckc(password="password")
        cfg_data_1 = self.cfg_file.read_text()
        self.ckc(password="password")
        cfg_data_2 = self.cfg_file.read_text()
        # Verify that calling w/ the same data keeps the same file contents.
        assert cfg_data_2 == cfg_data_1

    def test_efficient_updates(self):
        self.ckc(password="old_password")
        cfg_stat_1 = self.cfg_file.stat()
        self.ckc(password="old_password")
        cfg_stat_2 = self.cfg_file.stat()
        self.ckc(password="new_password")
        cfg_stat_3 = self.cfg_file.stat()
        # Verify that calling with the same data doesn't
        # modify the file at all, but that new data does
        assert cfg_stat_1.st_mtime == cfg_stat_2.st_mtime < cfg_stat_3.st_mtime

    def test_aws_iam(self):
        self.ckc(password="password", aws_iam_cluster_id="aws-cluster")
        assert self.cfg_file.exists()
        cfg_data_1 = self.cfg_file.read_text()
        assert "aws-cluster" in cfg_data_1

    def test_keystone(self):
        self.ckc(password="password", keystone=True)
        assert self.cfg_file.exists()
        cfg_data_1 = self.cfg_file.read_text()
        assert "keystone-user" in cfg_data_1
        assert "exec" in cfg_data_1

    def test_atomic_updates(self):
        self.ckc(password="old_password")
        with self.cfg_file.open("rt") as f:
            # Perform a write in the middle of reading
            self.ckc(password="new_password")
            # Read data from existing FH after new data was written
            cfg_data_1 = f.read()
        # Read updated data
        cfg_data_2 = self.cfg_file.read_text()
        # Verify that the in-progress read didn't get any of the new data
        assert cfg_data_1 != cfg_data_2
        assert "old_password" in cfg_data_1
        assert "new_password" in cfg_data_2

    @mock.patch("charmhelpers.core.hookenv.network_get", autospec=True)
    def test_get_ingress_address(self, network_get):
        network_get.return_value = {"ingress-addresses": ["1.2.3.4", "5.6.7.8"]}
        ingress = kubernetes_common.get_ingress_address("endpoint-name")
        assert ingress == "1.2.3.4"
        ingress = kubernetes_common.get_ingress_address("endpoint-name", ["1.2.3.4"])
        assert ingress == "5.6.7.8"
