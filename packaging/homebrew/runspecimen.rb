# Installs published v0.2.0-rc.12. Isolation, shared policy, and retain are
# unreleased in this working tree and are not in that sdist.
class Runspecimen < Formula
  include Language::Python::Virtualenv

  desc "Human-approved bounded local runs with provenance receipts"
  homepage "https://runspecimen.darashkevich.com/"
  url "https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.12/runspecimen-0.2.0rc12.tar.gz"
  sha256 "bf1f1a6223a1f65504a13f98bb1ddbad773dffd458bb6b5dcf32920c43c8bfed"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "0.2.0rc12", shell_output("#{bin}/runspecimen --version")
  end
end
