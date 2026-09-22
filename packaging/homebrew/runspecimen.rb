# Installs v0.2.0-rc.13. Opt-in isolation, policy, and retain are in that
# sdist. Default backend none does not confine the process.
class Runspecimen < Formula
  include Language::Python::Virtualenv

  desc "Human-approved bounded local runs with provenance receipts"
  homepage "https://runspecimen.darashkevich.com/"
  url "https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.13/runspecimen-0.2.0rc13.tar.gz"
  sha256 "0a807d65e73adfc2af2c8e5679706ed7c4d881ffefdc36e9222507cf5168f5c5"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "0.2.0rc13", shell_output("#{bin}/runspecimen --version")
  end
end
