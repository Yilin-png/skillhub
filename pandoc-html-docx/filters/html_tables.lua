--[[
html_tables.lua — 把 Markdown 中的原生 HTML <table> 转成 pandoc 原生 Table。

为什么需要：pandoc 的 docx writer 会丢弃 RawBlock(html)，而原生 Table
（pandoc ≥ 2.10 的复杂表格 AST）可以携带 colspan / rowspan，docx writer 会写成
gridSpan / vMerge。这样整篇文档只需 MD→DOCX 一次转换，脚注、公式（OMML）、
custom-style、交叉引用、citeproc 等 Markdown 特性都不再因 HTML 中转而丢失。

配合读取格式 `markdown-markdown_in_html_blocks` 使用：此时每个 <table>…</table>
是一个完整的 RawBlock。

另外兜底一种常见写法错误：<table> 前没有空行（或顶层缩进），pandoc 会把它解析成
段落内的 RawInline，docx 中整张表会静默消失。这里把这类段落拆开并恢复成表格
（lint 仍会提示作者补空行）。
]]

local TABLE_OPEN = '^%s*<[Tt][Aa][Bb][Ll][Ee][%s>/]'
local TABLE_ANY = '<[Tt][Aa][Bb][Ll][Ee][%s>/]'
local TABLE_CLOSE = '^%s*</[Tt][Aa][Bb][Ll][Ee]%s*>'

local recovered = 0

local function is_html(fmt)
  return fmt == 'html' or fmt == 'html5' or fmt == 'html4'
end

local function warn(msg)
  io.stderr:write('[html_tables] ' .. msg .. '\n')
end

-- pandoc（至少 3.1.x）的 HTML reader 对 <tbody> 里同时带 rowspan 与 colspan 的
-- <th> 会丢掉 colspan 并补一个空单元格，表格错位。<tbody> 中的 <th> 在 docx 里
-- 与 <td> 并无样式差别，因此解析前统一改成 <td>（<thead> 中的 <th> 不动）。
local function tbody_th_to_td(text)
  return (text:gsub('(<[Tt][Bb][Oo][Dd][Yy][^>]*>)(.-)(</[Tt][Bb][Oo][Dd][Yy]%s*>)',
    function(open, inner, close)
      inner = inner:gsub('<[Tt][Hh]([%s>])', '<td%1'):gsub('</[Tt][Hh]%s*>', '</td>')
      return open .. inner .. close
    end))
end

local function read_html(text)
  text = tbody_th_to_td(text)
  local ok, doc = pcall(pandoc.read, text, 'html')
  if not ok then
    warn('HTML 表格解析失败，已原样跳过：' .. tostring(doc))
    return nil
  end
  return doc.blocks
end

function RawBlock(el)
  if is_html(el.format) and el.text:match(TABLE_ANY) then
    return read_html(el.text)
  end
end

local function is_open(il)
  return il.t == 'RawInline' and is_html(il.format) and il.text:match(TABLE_OPEN)
end

local function is_close(il)
  return il.t == 'RawInline' and is_html(il.format) and il.text:match(TABLE_CLOSE)
end

local function trim_breaks(list)
  while #list > 0 and (list[#list].t == 'SoftBreak' or list[#list].t == 'Space'
      or list[#list].t == 'LineBreak') do
    table.remove(list)
  end
  while #list > 0 and (list[1].t == 'SoftBreak' or list[1].t == 'Space'
      or list[1].t == 'LineBreak') do
    table.remove(list, 1)
  end
  return list
end

local function split_inline_tables(el)
  if not pandoc.write then
    return nil -- pandoc < 2.17：无法恢复，交给 lint 报告
  end
  local has = false
  for _, il in ipairs(el.content) do
    if is_open(il) then has = true break end
  end
  if not has then return nil end

  local out, buf, tbl, depth = {}, {}, nil, 0
  local ctor = el.t == 'Para' and pandoc.Para or pandoc.Plain

  local function flush()
    buf = trim_breaks(buf)
    if #buf > 0 then table.insert(out, ctor(buf)) end
    buf = {}
  end

  for _, il in ipairs(el.content) do
    if depth == 0 then
      if is_open(il) then
        flush()
        tbl = { il }
        depth = 1
      else
        table.insert(buf, il)
      end
    else
      table.insert(tbl, il)
      if is_open(il) then
        depth = depth + 1
      elseif is_close(il) then
        depth = depth - 1
        if depth == 0 then
          local html = pandoc.write(pandoc.Pandoc({ pandoc.Plain(tbl) }), 'html')
          local blocks = read_html(html)
          if not blocks then return nil end
          for _, b in ipairs(blocks) do table.insert(out, b) end
          recovered = recovered + 1
          tbl = nil
        end
      end
    end
  end
  if depth ~= 0 then
    warn('发现未闭合的 <table>，该段落未处理')
    return nil
  end
  flush()
  return out
end

Para = split_inline_tables
Plain = split_inline_tables

function Pandoc(doc)
  if recovered > 0 then
    warn(string.format('已恢复 %d 张"前面缺空行/被缩进"的表格；请在 <table> 前后补空行', recovered))
  end
  return doc
end
