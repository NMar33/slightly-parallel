import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Markdown — compact, token-styled markdown for captured chat and entry
 * layers. Renders to React elements only (raw HTML in the source is
 * ignored by react-markdown's default), so captured agent/user text can
 * never inject markup into the page.
 */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="sp-md min-w-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p className="text-13 text-secondary leading-relaxed mb-8 last:mb-0">
              {children}
            </p>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-primary">{children}</strong>
          ),
          em: ({ children }) => <em>{children}</em>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-brand hover:underline break-all"
            >
              {children}
            </a>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-20 mb-8 last:mb-0 flex flex-col gap-2 text-13 text-secondary">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-20 mb-8 last:mb-0 flex flex-col gap-2 text-13 text-secondary">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed">{children}</li>
          ),
          h1: ({ children }) => (
            <h4 className="text-14 font-semibold text-primary mt-12 mb-4 first:mt-0">
              {children}
            </h4>
          ),
          h2: ({ children }) => (
            <h4 className="text-14 font-semibold text-primary mt-12 mb-4 first:mt-0">
              {children}
            </h4>
          ),
          h3: ({ children }) => (
            <h5 className="text-13 font-semibold text-primary mt-8 mb-4 first:mt-0">
              {children}
            </h5>
          ),
          code: ({ className, children }) => {
            const isBlock = /language-/.test(className ?? '')
            if (isBlock) {
              return (
                <code className="block text-12 font-mono text-secondary whitespace-pre overflow-x-auto">
                  {children}
                </code>
              )
            }
            return (
              <code className="text-12 font-mono text-secondary bg-elevated rounded-[4px] px-4 py-1">
                {children}
              </code>
            )
          },
          pre: ({ children }) => (
            <pre className="bg-elevated rounded-input p-12 mb-8 last:mb-0 overflow-x-auto">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-border-strong pl-12 text-tertiary mb-8 last:mb-0">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto mb-8 last:mb-0">
              <table className="text-12 text-secondary border-collapse">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="text-left font-semibold text-primary border-b border-border-default px-8 py-4">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border-subtle px-8 py-4 align-top">
              {children}
            </td>
          ),
          hr: () => <hr className="border-border-subtle my-8" />,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
