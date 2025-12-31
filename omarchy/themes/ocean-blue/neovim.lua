return {
    {
        "bjarneo/aether.nvim",
        name = "aether",
        priority = 1000,
        opts = {
            disable_italics = false,
            colors = {
                -- Monotone shades (base00-base07)
                base00 = "#091326", -- Default background
                base01 = "#667fae", -- Lighter background (status bars)
                base02 = "#091326", -- Selection background
                base03 = "#667fae", -- Comments, invisibles
                base04 = "#B0C6E6", -- Dark foreground
                base05 = "#f5f8fc", -- Default foreground
                base06 = "#f5f8fc", -- Light foreground
                base07 = "#B0C6E6", -- Light background

                -- Accent colors (base08-base0F)
                base08 = "#989790", -- Variables, errors, red
                base09 = "#c4c4bf", -- Integers, constants, orange
                base0A = "#7BA4D2", -- Classes, types, yellow
                base0B = "#79A7E0", -- Strings, green
                base0C = "#6E98CC", -- Support, regex, cyan
                base0D = "#749be1", -- Functions, keywords, blue
                base0E = "#70a0f5", -- Keywords, storage, magenta
                base0F = "#bdd3eb", -- Deprecated, brown/yellow
            },
        },
        config = function(_, opts)
            require("aether").setup(opts)
            vim.cmd.colorscheme("aether")

            -- Enable hot reload
            require("aether.hotreload").setup()
        end,
    },
    {
        "LazyVim/LazyVim",
        opts = {
            colorscheme = "aether",
        },
    },
}
