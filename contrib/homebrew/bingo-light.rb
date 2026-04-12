class BingoLight < Formula
  desc "Fork maintenance for AI agents — patch stack on top of upstream, one command to sync"
  homepage "https://github.com/DanOps-1/bingo-light"
  url "https://github.com/DanOps-1/bingo-light/archive/refs/tags/v2.0.0.tar.gz"
  # sha256 "UPDATE_AFTER_RELEASE"
  license "MIT"

  depends_on "git"
  depends_on "python@3"

  def install
    bin.install "bingo-light"
    bin.install "bingo_core.py"
    bin.install "mcp-server.py" => "bingo-light-mcp"
    bin.install "agent.py" => "bingo-light-agent"
    bin.install "tui.py" => "bingo-light-tui"

    bash_completion.install "completions/bingo-light.bash" => "bingo-light"
    zsh_completion.install "completions/bingo-light.zsh" => "_bingo-light"
    fish_completion.install "completions/bingo-light.fish"
  end

  test do
    system "#{bin}/bingo-light", "--version"
  end
end
