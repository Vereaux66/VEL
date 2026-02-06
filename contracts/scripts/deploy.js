// VEL Trading Platform - Contract Deployment Script
// Usage: npx hardhat run scripts/deploy.js --network <network>

const hre = require("hardhat");

async function main() {
  console.log("═".repeat(60));
  console.log("VEL Trading Platform - Contract Deployment");
  console.log("═".repeat(60));
  
  // Get deployer info
  const [deployer] = await hre.ethers.getSigners();
  console.log("\nDeployer:", deployer.address);
  
  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log("Balance:", hre.ethers.formatEther(balance), "ETH");
  
  // Network info
  const network = await hre.ethers.provider.getNetwork();
  console.log("Network:", network.name, `(chainId: ${network.chainId})`);
  
  // Deployment parameters
  const maxSlippageBps = 100; // 1% max slippage
  const minDeadlineOffset = 60; // 60 seconds minimum deadline
  
  console.log("\n" + "─".repeat(60));
  console.log("Deployment Parameters:");
  console.log("  Max Slippage:", maxSlippageBps, "bps (", maxSlippageBps / 100, "%)");
  console.log("  Min Deadline Offset:", minDeadlineOffset, "seconds");
  console.log("─".repeat(60) + "\n");
  
  // Deploy VELTradeExecutor
  console.log("Deploying VELTradeExecutor...");
  
  const VELTradeExecutor = await hre.ethers.getContractFactory("VELTradeExecutor");
  const executor = await VELTradeExecutor.deploy(
    maxSlippageBps,
    minDeadlineOffset
  );
  
  await executor.waitForDeployment();
  const executorAddress = await executor.getAddress();
  
  console.log("✓ VELTradeExecutor deployed to:", executorAddress);
  
  // Get deployment transaction
  const deployTx = executor.deploymentTransaction();
  console.log("  Transaction hash:", deployTx.hash);
  console.log("  Gas used:", (await deployTx.wait()).gasUsed.toString());
  
  // Verify contract on Etherscan (if not local)
  if (network.chainId !== 31337n && network.chainId !== 1337n) {
    console.log("\nWaiting for block confirmations...");
    await deployTx.wait(5); // Wait for 5 confirmations
    
    console.log("Verifying contract on Etherscan...");
    try {
      await hre.run("verify:verify", {
        address: executorAddress,
        constructorArguments: [maxSlippageBps, minDeadlineOffset],
      });
      console.log("✓ Contract verified on Etherscan");
    } catch (error) {
      if (error.message.includes("Already Verified")) {
        console.log("✓ Contract already verified");
      } else {
        console.log("⚠ Verification failed:", error.message);
      }
    }
  }
  
  // Post-deployment configuration
  console.log("\n" + "─".repeat(60));
  console.log("Post-Deployment Configuration");
  console.log("─".repeat(60));
  
  // Approve common DEX routers based on network
  const routers = getRoutersForNetwork(network.chainId);
  
  for (const [name, address] of Object.entries(routers)) {
    try {
      const tx = await executor.setRouterApproval(address, true);
      await tx.wait();
      console.log(`✓ Approved router: ${name} (${address})`);
    } catch (error) {
      console.log(`⚠ Failed to approve ${name}:`, error.message);
    }
  }
  
  // Approve common tokens
  const tokens = getTokensForNetwork(network.chainId);
  
  for (const [name, address] of Object.entries(tokens)) {
    try {
      const tx = await executor.setTokenApproval(address, true);
      await tx.wait();
      console.log(`✓ Approved token: ${name} (${address})`);
    } catch (error) {
      console.log(`⚠ Failed to approve ${name}:`, error.message);
    }
  }
  
  // Summary
  console.log("\n" + "═".repeat(60));
  console.log("Deployment Summary");
  console.log("═".repeat(60));
  console.log("VELTradeExecutor:", executorAddress);
  console.log("Owner:", deployer.address);
  console.log("Network:", network.name);
  console.log("═".repeat(60));
  
  // Save deployment info
  const deploymentInfo = {
    network: network.name,
    chainId: network.chainId.toString(),
    contracts: {
      VELTradeExecutor: executorAddress,
    },
    deployer: deployer.address,
    timestamp: new Date().toISOString(),
    parameters: {
      maxSlippageBps,
      minDeadlineOffset,
    },
    approvedRouters: routers,
    approvedTokens: tokens,
  };
  
  const fs = require("fs");
  const deploymentsDir = "./deployments";
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir);
  }
  
  const deploymentFile = `${deploymentsDir}/${network.name}-${Date.now()}.json`;
  fs.writeFileSync(deploymentFile, JSON.stringify(deploymentInfo, null, 2));
  console.log("\nDeployment info saved to:", deploymentFile);
}

// Helper: Get DEX routers for a given network
function getRoutersForNetwork(chainId) {
  const routers = {
    // Ethereum Mainnet
    1: {
      "Uniswap V3 Router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
      "Uniswap V2 Router": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
      "SushiSwap Router": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
    },
    // Sepolia Testnet
    11155111: {
      "Uniswap V3 Router": "0x3bFA4769FB09eefC5a80d6E87c3B9C650f7Ae48E",
    },
    // Arbitrum
    42161: {
      "Uniswap V3 Router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
      "SushiSwap Router": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
    },
    // Polygon
    137: {
      "Uniswap V3 Router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
      "QuickSwap Router": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
    },
    // BSC
    56: {
      "PancakeSwap Router": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
    },
    // Base
    8453: {
      "Uniswap V3 Router": "0x2626664c2603336E57B271c5C0b26F421741e481",
    },
  };
  
  return routers[Number(chainId)] || {};
}

// Helper: Get common tokens for a given network
function getTokensForNetwork(chainId) {
  const tokens = {
    // Ethereum Mainnet
    1: {
      "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
      "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
      "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
      "DAI": "0x6B175474E89094C44Da98b954EescdeCB5DB3357",
      "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    },
    // Sepolia
    11155111: {
      "WETH": "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",
    },
    // Arbitrum
    42161: {
      "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
      "USDC": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
      "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    },
    // Polygon
    137: {
      "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
      "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
      "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
    },
    // BSC
    56: {
      "WBNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
      "USDT": "0x55d398326f99059fF775485246999027B3197955",
      "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    },
    // Base
    8453: {
      "WETH": "0x4200000000000000000000000000000000000006",
      "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
    },
  };
  
  return tokens[Number(chainId)] || {};
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
