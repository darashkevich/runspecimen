# Installs v0.2.0-rc.15. Opt-in isolation, policy, and retain are in that
# sdist. Default backend none does not confine the process.
class Runspecimen < Formula
  include Language::Python::Virtualenv

  desc "Human-approved bounded local runs with provenance receipts"
  homepage "https://runspecimen.darashkevich.com/"
  url "https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.15/runspecimen-0.2.0rc15.tar.gz"
  sha256 "(to be determined after release)"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "0.2.0rc15", shell_output("#{bin}/runspecimen --version")
  end
end
