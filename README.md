# datadog-docs-mcp

Datadog の公式 LLM ドキュメント（[llms.txt](https://docs.datadoghq.com/llms.txt)）を MCP（Model Context Protocol）経由で利用できるサーバーです。

13,000 件以上の Datadog ドキュメントの検索・閲覧を LLM から直接行えます。

## 提供ツール

| ツール | 説明 |
|--------|------|
| `list_documents` | ドキュメント一覧の取得（セクション絞り込み・ページネーション対応） |
| `read_document` | 指定 URL のドキュメントを Markdown で取得 |
| `read_document_chunk` | 大きなドキュメントのチャンク読み込み |
| `search_documents` | キーワードでドキュメント検索（スコアリング方式） |
| `get_index_sections` | セクション一覧と件数を表示 |
| `refresh_index` | キャッシュしたインデックスを強制リフレッシュ |

## セットアップ

### 前提条件

- [uv](https://docs.astral.sh/uv/getting-started/installation/) がインストールされていること


```json
{
  "mcpServers": {
    "datadog-docs": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/onodera-yu/datadog-docs-mcp", "datadog-docs-mcp"]
    }
  }
}
```

### Windows の場合

`uvx` が見つからない場合はフルパスを指定するか、`cmd` 経由で実行してください。

```json
{
  "mcpServers": {
    "datadog-docs": {
      "command": "cmd",
      "args": ["/c", "uvx", "--from", "git+https://github.com/onodera-yu/datadog-docs-mcp", "datadog-docs-mcp"]
    }
  }
}
```

Windows への uv のインストール（PowerShell）:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

### その他の MCP 対応クライアント

stdio トランスポートで `datadog-docs-mcp` コマンドを実行する設定であれば、どのクライアントでも動作します。

## 仕組み

- Datadog が公開している [`llms.txt`](https://docs.datadoghq.com/llms.txt) をパースしてインデックスを構築
- 各ドキュメントは Datadog のサイトからリアルタイムに取得（コンテンツの再配布は行いません）
- インデックスはメモリ内にキャッシュされ、`refresh_index` で更新可能

## ローカル開発

```bash
git clone https://github.com/onodera-yu/datadog-docs-mcp.git
cd datadog-docs-mcp
uv sync
uv run datadog-docs-mcp
```

## ライセンス

MIT
