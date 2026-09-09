# ゲーム実機確認・採用記録

記録日: 2026-09-09。報告者: プロジェクト所有者（ユーザー）。
ユーザーが生成済みr6 corrected local Modをゲームへコピーし、以下の7名称を実機確認した。

| 名称 | 結果 |
|---|---|
| 聖なる箱 | PASS |
| 火炎船 | PASS |
| 火箭術 | PASS |
| イェニチェリ | PASS |
| エリート イェニチェリ | PASS |
| 火箭車 | PASS |
| 神機箭 | PASS |

さらにユーザーは手動local Modへ `170300 "メイン メニューに戻る"` を追加し、該当UI表示がその値へ変化することを確認した。これにより、170300が該当表示を所有することと、採用値の実機表示を確認済みとする。

現行記録の採用入力は名称104裁定＋文脈付き全文29裁定＝133裁定と、人間layout裁定13件。
記録対象の計画は387 operations（全文229 / span158）、387 String IDs。
正式な確認記録は [reviews/game-validation.json](../reviews/game-validation.json) に保存する。
名称・全文・layoutの既存署名付き裁定は、この表示確認を理由に再署名していない。

現行387 ID差分ファイルへ次のSHA-256で結び付ける。

```text
15b8c695328d045037a7d2881c985d5384ddd3f70ea4d09abe12a4cf2e11dcee
```

7名称はr6 correctedの386-entry差分（SHA-256 `f85dd227d5243af3dcc4819ff74f6daf953efe1c6d6bee517d7224df7071e11e`）で確認された。170300はその後の手動追加で確認された。現行hashは、同じ既存386値と正式採用した170300を既存pipelineで生成した387-entry差分への対応付けであり、インストール済みファイルのhashを実測した記録ではない。
ゲームbuild、実際の確認日時、解像度、スクリーンショットは報告されていないため補完しない。
全387 ID、13 layout位置、全チェックリスト項目を個別に確認したとは記録しない。
これらの詳細確認票は [CHECKLIST](phase1f-checklist.md) を引き続き利用できる。

Mod packageのmanifestは、生成翻訳のhashがこの記録と一致する場合に
`runtime_verified=true`、`runtime_validation.status=matching_user_report` とする。
確認範囲と報告の主体も併記する。hashが変われば過去の実機確認を自動継承しない。
`verification.game_launched=false` / `installed=false` は生成ツールが実行しなかったことを示し、人間の確認記録と区別する。

今回の正式再生成先は `reports/final/historical-restore-r7-ui-170300-final/`、`dist/historical-restore-r7-ui-170300-final-mod/`、`dist/historical-restore-r7-ui-170300-final-local-mod/`。
source・署名付き裁定を再照合し、全pytest、scope/patch/layout、Modのverify-onlyと再生成一致を確認する。
ゲームへのアクセス・コピー・起動、pushは行わない。
