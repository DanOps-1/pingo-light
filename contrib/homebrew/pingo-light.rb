class PingoLight < Formula
  desc "AI-native fork maintenance tool — manage patch stacks on top of upstream"
  homepage "https://github.com/DanOps-1/pingo-light"
  url "https://github.com/DanOps-1/pingo-light/archive/refs/tags/v1.0.0.tar.gz"
  # sha256 "UPDATE_WITH_ACTUAL_SHA256"
  license "MIT"

  depends_on "git"
  depends_on "python@3" => :optional # for MCP server and agent

  def install
    bin.install "pingo-light"
    bin.install "mcp-server.py" => "pingo-light-mcp"
    bin.install "agent.py" => "pingo-light-agent"
    bin.install "tui.py" => "pingo-light-tui"

    bash_completion.install "completions/pingo-light.bash" => "pingo-light"
    zsh_completion.install "completions/pingo-light.zsh" => "_pingo-light"
    fish_completion.install "completions/pingo-light.fish"
  end

  test do
    system "#{bin}/pingo-light", "--version"
  end
end
