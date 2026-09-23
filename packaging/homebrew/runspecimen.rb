# Installs v0.2.0-rc.14. Opt-in isolation, policy, and retain are in that
# sdist. Default backend none does not confine the process.
class Runspecimen < Formula
  include Language::Python::Virtualenv

  desc "Human-approved bounded local runs with provenance receipts"
  homepage "https://runspecimen.darashkevich.com/"
  url "https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.14/runspecimen-0.2.0rc14.tar.gz"
  sha256 "6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "0.2.0rc14", shell_output("#{bin}/runspecimen --version")
  end
end
