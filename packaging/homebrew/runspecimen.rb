# Installs 0.2.0rc16 from the published PyPI sdist. Opt-in isolation, policy,
# retain, and evidence-expansion commands are in that sdist. Default backend
# none does not confine the process.
class Runspecimen < Formula
  include Language::Python::Virtualenv

  desc "Human-approved bounded local runs with provenance receipts"
  homepage "https://runspecimen.darashkevich.com/"
  url "https://files.pythonhosted.org/packages/73/b5/963b42b37a0a932e22496f7da4d3c289fef01b1a87d31f6914571ed3081d/runspecimen-0.2.0rc16.tar.gz"
  sha256 "83625441d316816107087870525a88d20cd42b61c69e7e398ce95cdcc3fe31d4"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "0.2.0rc16", shell_output("#{bin}/runspecimen --version")
  end
end
