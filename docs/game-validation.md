# ゲーム実機確認・採用記録

記録日: 2026-09-09。報告者: プロジェクト所有者（ユーザー）。
ユーザーから「ゲーム上での表示確認が完了し、問題ありませんでした」と報告を受けた。
以下の10名称を実機確認済みとして記録する。

| 名称 | 結果 |
|---|---|
| 火箭車 | PASS |
| 重装火箭車 | PASS |
| 火箭術 | PASS |
| 神機箭 | PASS |
| トルコ | PASS |
| ローマ | PASS |
| 蜀 | PASS |
| ムイスカ | PASS |
| マプチェ | PASS |
| トゥピ | PASS |

現在の採用入力は名称103裁定＋文脈付き全文28裁定＝131裁定と、人間layout裁定13件。
計画は385 operations（全文227 / span158）、385 String IDs。
正式な確認記録は [reviews/game-validation.json](../reviews/game-validation.json) に保存する。
名称・全文・layoutの既存署名付き裁定は、この表示確認を理由に再署名していない。

報告直前に生成した385 ID差分ファイルへ次のSHA-256で結び付ける。

```text
fd8eebbe726e36ca1c3a6173427b2ec95394950007c26b10e5bff1c24a57374c
```

これは生成成果物への対応付けであり、インストール済みファイルのhashを実測した記録ではない。
ゲームbuild、実際の確認日時、解像度、スクリーンショットは報告されていないため補完しない。
全385 ID、13 layout位置、全チェックリスト項目を個別に確認したとは記録しない。
これらの詳細確認票は [CHECKLIST](phase1f-checklist.md) を引き続き利用できる。

Mod packageのmanifestは、生成翻訳のhashがこの記録と一致する場合に
`runtime_verified=true`、`runtime_validation.status=matching_user_report` とする。
確認範囲と報告の主体も併記する。hashが変われば過去の実機確認を自動継承しない。
`verification.game_launched=false` / `installed=false` は生成ツールが実行しなかったことを示し、人間の確認記録と区別する。

最終再生成先は `reports/final/`、`dist/final-mod/`、`dist/final-local-mod/`。
source・署名付き裁定を再照合し、全pytest、scope/patch/layout、Modのverify-onlyと再生成一致を確認してcommitする。
ゲームへのアクセス・コピー・起動、pushは行わない。
