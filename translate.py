import openai, re, os, sys

if len(sys.argv) == 1:
    print("usage: translate.py prompt.txt target.tex")
    print("before use, please fill in the api_key.")
    exit(1)

# model: deepseek-chat
client = openai.OpenAI(
    api_key = "",
    base_url = "https://api.deepseek.com/v1",
    timeout = 300
)

# model: kimi-k2-0905-preview
client1 = openai.OpenAI(
    api_key = "",
    base_url = "https://api.moonshot.cn/v1",
    timeout = 300
)

# model: doubao-seed-code-preview-251028
client2 = openai.OpenAI(
    api_key = "",
    base_url = "https://ark.cn-beijing.volces.com/api/v3/",
    timeout = 300
)

def print_bytes(str):
    num_bytes = len(str)
    if num_bytes < 1024:
        return f"{num_bytes} B"
    else:
        return f"{num_bytes / 1024:.2f} KB"

TOKEN_RE = re.compile(
    r'(?P<begin>\\begin\{[A-Za-z]+\})'
    r'|(?P<end>\\end\{[A-Za-z]+\})'
    r'|(?P<prefix>^\s*\\pnum\s*$)',
    re.MULTILINE
)

def split_latexScopes(src):
    fragments = []
    stack = []
    last_end = 0
    n = len(src)

    for m in TOKEN_RE.finditer(src):
        tok = m.groupdict()
        pos = m.start()
        if tok['prefix']:
            if not stack:
                gap = src[last_end:pos].rstrip()
                if gap:
                    fragments.append(gap)
                    last_end = pos
            continue
        if tok['begin']:
            env = tok['begin'][7:-1]
            stack.append((env, pos))
            continue
        if tok['end']:
            env = tok['end'][5:-1]
            if stack and stack[-1][0] == env:
                _, begin_pos = stack.pop()
                if not stack:
                    end_pos = m.end()
                    fragments.append(src[last_end:end_pos])
                    last_end = end_pos
            continue

    tail = src[last_end:].rstrip()
    if tail:
        fragments.append(tail)

    return fragments

prompt_path, tex_path = sys.argv[1:3]

with open(prompt_path, encoding='utf-8') as f:
    prompt = f.read()
with open(tex_path, encoding='utf-8') as f:
    text = f.read()

parts = [""]
for s in re.split(r'(?=\n\n\\rSec[01234])', text):
    if (len(s) > 2048):
        for s1 in split_latexScopes(s):
            if len(s1) > 8 * 1024:
                parts.append(s1)
            else:
                if (len(parts[-1]) < 512):
                    parts[-1] += s1
                else:
                    parts.append(s1)
    else:
        if (len(parts[-1]) < 512):
            parts[-1] += s
        else:
            parts.append(s)

for s in parts:
    if (len(s) > (8 * 1024)):
        print(f"Warning: Data too large for single request, revise split algorithm.\nCurrent size: {len(s)}, content: {s[0: 512]}")

os.makedirs('backup', exist_ok=True)

translated = []
print(f"Total: {len(parts)}, size: {print_bytes(text)}.")
for idx, part in enumerate(parts, 1):
    print(f"Current: {idx}, size: {print_bytes(part)}.")

    prefix, _ = os.path.splitext(os.path.basename(tex_path))
    backup_path = f'./backup/{prefix}_{idx}.tex'

    if os.path.exists(backup_path):
        with open(backup_path, 'r', encoding='utf-8') as f:
            content = f.read()
            translated.append(content)
            print(f"Restore backup: {idx}, File: {backup_path}.")
            continue

    content = part

    if len(content) < 16 * 1024:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "翻译tex文档（只负责翻译，不负责修正tex，假定所有tex命令都是正确的），确保译文满足以下要求，对照原文检查格式是否正确（输出修正后的原始tex译文，不输出markdown）\n翻译要求：\n" + prompt + "\n原文：\n" + part}
            ],
            temperature=2.0
        )
        content = resp.choices[0].message.content

    if len(content) < 8 * 1024:
        resp1 = client1.chat.completions.create(
            model="kimi-k2-0905-preview",
            messages=[
                {"role": "user", "content": "通过对比原文和译文修复翻译后的tex文档，修复损坏的tex命令（tex命令格式为反斜线+英文字母命令名，如果没有参数则在命令名后有空格），添加缺失的翻译（输出修正后的原始tex译文，不输出markdown）\n原文：\n" + part + "\n译文：\n" + content}
            ],
            temperature=1.0
        )
    
        content = resp1.choices[0].message.content.rstrip('\n') + "\n\n"

    translated.append(content)

    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)

base, _ = os.path.splitext(tex_path)
os.rename(tex_path, base + "_old.tex")
out_path = base + ".tex"
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(''.join(translated))
