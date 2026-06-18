# Project Context: The Beer Fund Bot

## What we're trying to do

We're building a small copy-trading bot on Solana that mirrors smart money wallets. Nothing fancy, nothing leveraged, nothing that could ruin anyone's week. Small capital — genuinely small — with one goal: prove that a couple of outsiders can build something that consistently skims a profit off DEX trading without being plugged into the insider machine. If it works, the winnings buy beers for the mates. That's the whole ambition. The beer fund is the scoreboard.

## Why some people can do it

Let's be honest about why the people we've been watching actually make money. It's not magic, and it's mostly not skill in the way they'd like you to believe:

- **Information asymmetry.** Insiders, VC wallets, and launch teams know about tokens before anyone else does. They're buying before the token technically exists for the rest of us.
- **Infrastructure.** Sub-millisecond execution, private RPC nodes, MEV bundles via Jito. Their trades land in the same block as the news. Ours land three blocks later if we're lucky.
- **Capital scale.** When you're moving six figures, a 3% move pays the mortgage. Small percentage wins are meaningful at size.
- **Network.** They're in the right Telegram and Discord groups where alpha gets shared early. By the time it reaches public channels, it's exit liquidity recruitment.
- **Pattern-matching.** They've watched thousands of launches. They can smell a rug from the deployer wallet alone. That experience is real and we don't have it yet.

## What's stopping the average person

This is the part we need to re-read when we're feeling cocky:

- **Survivorship bias is brutal.** We see the screenshots of the wins. Nobody posts the forty losses behind each one.
- **By the time a token trends on DexScreener, the early money has already made its gains.** Trending is the finish line, not the starting gun.
- **Public "smart money" leaderboards are crowded.** By the time we're copying a wallet, so is everyone else — and the wallet's edge erodes with every copier.
- **Free RPC nodes have latency** that quietly costs us on fast-moving trades. Seconds matter, and free infrastructure gives them away.
- **Most memecoins go to zero.** Not some — most. Without tight risk rules, one bad trade wipes the entire fund.
- **Emotions.** Panic selling at the bottom, holding losers because "it'll come back." Every novice does it. We would too, which is exactly why a bot trades and we don't.

## Why we can still compete

Here's the honest case for why this isn't hopeless:

- **Copy trading on Solana is timing-tolerant.** We're not racing snipers for the same block. If a good wallet enters and the token has legs, entering seconds later still works. We need seconds, not milliseconds — and seconds are achievable.
- **Small capital is an advantage.** We can trade tokens with liquidity so thin that whales literally can't touch them without moving the price against themselves. Our size lets us go where they can't.
- **Automation removes the emotional trades.** The bot doesn't panic, doesn't get greedy, doesn't revenge-trade at 2am.
- **The maths works at modest win rates.** With decent wallet selection and disciplined exits at 2–5x targets, we don't need to be right most of the time. We need to be right enough, and cut losers fast.

## The approach

- Custom bot in **Python or Node.js** — ours, so we understand every line.
- **Jupiter API** for swap execution.
- **Helius RPC** for fast, reliable chain access — we pay for the node so latency doesn't eat us.
- **GMGN.ai** to identify and vet the wallets worth copying — fresh, consistent, not already swarmed.
- **Hard exit rules baked in from day one.** Stop-losses, take-profit targets, and position sizing are code, not vibes. Non-negotiable.

## The goal

We're not trying to get rich. We're trying to build something that *works* — to understand this game from the inside instead of pressing our noses against the glass. The insiders win because of access we'll never have. Fine. We'll win, modestly, with discipline, small-size advantages, and software we built ourselves.

If at the end of this we've got a bot that grinds out steady small wins and a few rounds of beers on the table, we've proven the point: you don't have to be one of the cool kids. You just have to be smart, honest about the odds, and stubborn.
