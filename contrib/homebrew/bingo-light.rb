class BingoLight < Formula
  desc "AI-native fork maintenance tool — manage patch stacks on top of upstream"
  homepage "https://github.com/DanOps-1/bingo-light"
  url "https://github.com/DanOps-1/bingo-light/archive/refs/tags/v1.1.0.tar.gz"
  # sha256 "UPDATE_WITH_ACTUAL_SHA256"
  license "MIT"

  depends_on "git"
  depends_on "python@3" => :optional # for MCP server and agent

  def install
    bin.install "bingo-light"
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
