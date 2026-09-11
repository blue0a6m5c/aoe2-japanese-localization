# glossary（正式裁定の生成ビュー）

翻訳裁定の唯一の正本は `decisions/` です。

[terms.md](terms.md) は `decisions/translations.json` にある全裁定を人間が読みやすい形へ変換した生成ビューです。第二の正本ではなく、直接編集してはいけません。

次の Production build によって Mod と一緒に再生成されます。

``` console
python -m tools.localization build
```
