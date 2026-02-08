// VEL Trading Platform - Complete Contract Suite Deployment Script
// Usage: npx hardhat run scripts/deploy.js --network <network>

const hre = require("hardhat");
const fs = require("fs");
const crypto = require("crypto");

async function main() {
  console.log("═".repeat(60));
  console.log("VEL Trading Platform - Complete Contract Suite Deployment");
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
  const bridgeFeeBps = 30; // 0.3% bridge fee
  const protocolFeeBps = 10; // 0.1% protocol fee
  const performanceFeeBps = 2000; // 20% performance fee
  const managementFeeBps = 100; // 1% management fee
  const revealDelay = 3; // 3 blocks reveal delay
  const relayerFeeBps = 5; // 0.05% relayer fee
  
  console.log("\n" + "─".repeat(60));
  console.log("Deployment Parameters:");
  console.log("  Max Slippage:", maxSlippageBps, "bps (", maxSlippageBps / 100, "%)");
  console.log("  Min Deadline Offset:", minDeadlineOffset, "seconds");
  console.log("  Bridge Fee:", bridgeFeeBps, "bps");
  console.log("  Protocol Fee:", protocolFeeBps, "bps");
  console.log("─".repeat(60) + "\n");
  
  const deployedContracts = {};
  
  // 1. Deploy VELTradeExecutor
  console.log("1. Deploying VELTradeExecutor...");
  const VELTradeExecutor = await hre.ethers.getContractFactory("VELTradeExecutor");
  const executor = await VELTradeExecutor.deploy(maxSlippageBps, minDeadlineOffset);
  await executor.waitForDeployment();
  const executorAddress = await executor.getAddress();
  deployedContracts.VELTradeExecutor = executorAddress;
  console.log("✓ VELTradeExecutor deployed to:", executorAddress);
  
  // 2. Deploy VELMultiDEXRouter
  console.log("\n2. Deploying VELMultiDEXRouter...");
  const VELMultiDEXRouter = await hre.ethers.getContractFactory("VELMultiDEXRouter");
  const router = await VELMultiDEXRouter.deploy(
    maxSlippageBps,
    minDeadlineOffset,
    deployer.address, // fee recipient
    protocolFeeBps
  );
  await router.waitForDeployment();
  const routerAddress = await router.getAddress();
  deployedContracts.VELMultiDEXRouter = routerAddress;
  console.log("✓ VELMultiDEXRouter deployed to:", routerAddress);
  
  // 3. Deploy VELPooledTradingVault
  console.log("\n3. Deploying VELPooledTradingVault...");
  // Get USDC address for the network (or use a placeholder for testing)
  const usdcAddress = getUSDCForNetwork(network.chainId) || deployer.address;
  const VELPooledTradingVault = await hre.ethers.getContractFactory("VELPooledTradingVault");
  const vault = await VELPooledTradingVault.deploy(
    usdcAddress,
    6, // USDC decimals
    deployer.address, // trader
    deployer.address, // fee recipient
    performanceFeeBps,
    managementFeeBps
  );
  await vault.waitForDeployment();
  const vaultAddress = await vault.getAddress();
  deployedContracts.VELPooledTradingVault = vaultAddress;
  console.log("✓ VELPooledTradingVault deployed to:", vaultAddress);
  
  // 4. Deploy VELCrosschainBridge
  console.log("\n4. Deploying VELCrosschainBridge...");
  // Use deployer as initial validator for testing
  const initialValidators = [deployer.address];
  // Add a second validator if we have more signers
  const signers = await hre.ethers.getSigners();
  if (signers.length > 1) {
    initialValidators.push(signers[1].address);
  } else {
    // Create a deterministic second validator address for testing
    initialValidators.push("0x0000000000000000000000000000000000000001");
  }
  
  const VELCrosschainBridge = await hre.ethers.getContractFactory("VELCrosschainBridge");
  const bridge = await VELCrosschainBridge.deploy(
    network.chainId,
    bridgeFeeBps,
    deployer.address, // fee recipient
    initialValidators,
    1 // required signatures (1 for testing, increase in production)
  );
  await bridge.waitForDeployment();
  const bridgeAddress = await bridge.getAddress();
  deployedContracts.VELCrosschainBridge = bridgeAddress;
  console.log("✓ VELCrosschainBridge deployed to:", bridgeAddress);
  
  // 5. Deploy VELAtomicSwapHTLC
  console.log("\n5. Deploying VELAtomicSwapHTLC...");
  const VELAtomicSwapHTLC = await hre.ethers.getContractFactory("VELAtomicSwapHTLC");
  const htlc = await VELAtomicSwapHTLC.deploy(network.chainId);
  await htlc.waitForDeployment();
  const htlcAddress = await htlc.getAddress();
  deployedContracts.VELAtomicSwapHTLC = htlcAddress;
  console.log("✓ VELAtomicSwapHTLC deployed to:", htlcAddress);
  
  // 6. Deploy VELAnonymousOrderExecutor
  console.log("\n6. Deploying VELAnonymousOrderExecutor...");
  const VELAnonymousOrderExecutor = await hre.ethers.getContractFactory("VELAnonymousOrderExecutor");
  const anonymousExecutor = await VELAnonymousOrderExecutor.deploy(
    revealDelay,
    relayerFeeBps,
    deployer.address // fee recipient
  );
  await anonymousExecutor.waitForDeployment();
  const anonymousExecutorAddress = await anonymousExecutor.getAddress();
  deployedContracts.VELAnonymousOrderExecutor = anonymousExecutorAddress;
  console.log("✓ VELAnonymousOrderExecutor deployed to:", anonymousExecutorAddress);
  
  // Get deployment transaction for VELTradeExecutor (for gas info)
  const deployTx = executor.deploymentTransaction();
  console.log("\n  Sample Transaction hash:", deployTx.hash);
  console.log("  Gas used:", (await deployTx.wait()).gasUsed.toString());
  
  // Verify contracts on Etherscan (if not local)
  if (network.chainId !== 31337n && network.chainId !== 1337n) {
    console.log("\nWaiting for block confirmations...");
    await deployTx.wait(5); // Wait for 5 confirmations
    
    console.log("Verifying contracts on Etherscan...");
    
    const contractsToVerify = [
      { name: "VELTradeExecutor", address: executorAddress, args: [maxSlippageBps, minDeadlineOffset] },
      { name: "VELMultiDEXRouter", address: routerAddress, args: [maxSlippageBps, minDeadlineOffset, deployer.address, protocolFeeBps] },
      { name: "VELPooledTradingVault", address: vaultAddress, args: [usdcAddress, 6, deployer.address, deployer.address, performanceFeeBps, managementFeeBps] },
      { name: "VELCrosschainBridge", address: bridgeAddress, args: [network.chainId, bridgeFeeBps, deployer.address, initialValidators, 1] },
      { name: "VELAtomicSwapHTLC", address: htlcAddress, args: [network.chainId] },
      { name: "VELAnonymousOrderExecutor", address: anonymousExecutorAddress, args: [revealDelay, relayerFeeBps, deployer.address] },
    ];
    
    for (const contract of contractsToVerify) {
      try {
        await hre.run("verify:verify", {
          address: contract.address,
          constructorArguments: contract.args,
        });
        console.log(`✓ ${contract.name} verified on Etherscan`);
      } catch (error) {
        if (error.message.includes("Already Verified")) {
          console.log(`✓ ${contract.name} already verified`);
        } else {
          console.log(`⚠ ${contract.name} verification failed:`, error.message);
        }
      }
    }
  }
  
  // Post-deployment configuration
  console.log("\n" + "─".repeat(60));
  console.log("Post-Deployment Configuration");
  console.log("─".repeat(60));
  
  // Approve common DEX routers based on network
  const routers = getRoutersForNetwork(network.chainId);
  
  // Configure VELTradeExecutor
  console.log("\nConfiguring VELTradeExecutor...");
  for (const [name, address] of Object.entries(routers)) {
    try {
      const tx = await executor.setRouterApproval(address, true);
      await tx.wait();
      console.log(`✓ Approved router: ${name} (${address})`);
    } catch (error) {
      console.log(`⚠ Failed to approve ${name}:`, error.message);
    }
  }
  
  // Configure VELMultiDEXRouter
  console.log("\nConfiguring VELMultiDEXRouter...");
  for (const [name, address] of Object.entries(routers)) {
    try {
      const dexId = hre.ethers.keccak256(hre.ethers.toUtf8Bytes(name));
      const tx = await router.registerDEX(dexId, address, 0, 150000); // 0 = UNISWAP_V2 type, 150k gas overhead
      await tx.wait();
      console.log(`✓ Registered DEX: ${name}`);
    } catch (error) {
      console.log(`⚠ Failed to register ${name}:`, error.message);
    }
  }
  
  // Configure VELAnonymousOrderExecutor
  console.log("\nConfiguring VELAnonymousOrderExecutor...");
  for (const [name, address] of Object.entries(routers)) {
    try {
      const tx = await anonymousExecutor.setRouter(address, true);
      await tx.wait();
      console.log(`✓ Approved router for anonymous execution: ${name}`);
    } catch (error) {
      console.log(`⚠ Failed to approve router ${name}:`, error.message);
    }
  }
  
  // Approve common tokens
  const tokens = getTokensForNetwork(network.chainId);
  
  console.log("\nApproving tokens across all contracts...");
  for (const [name, address] of Object.entries(tokens)) {
    try {
      // VELTradeExecutor
      let tx = await executor.setTokenApproval(address, true);
      await tx.wait();
      
      // VELMultiDEXRouter
      tx = await router.setTokenApproval(address, true);
      await tx.wait();
      
      // VELAtomicSwapHTLC
      tx = await htlc.setTokenApproval(address, true);
      await tx.wait();
      
      // VELAnonymousOrderExecutor
      tx = await anonymousExecutor.setToken(address, true);
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
  console.log("VELTradeExecutor:        ", executorAddress);
  console.log("VELMultiDEXRouter:       ", routerAddress);
  console.log("VELPooledTradingVault:   ", vaultAddress);
  console.log("VELCrosschainBridge:     ", bridgeAddress);
  console.log("VELAtomicSwapHTLC:       ", htlcAddress);
  console.log("VELAnonymousOrderExecutor:", anonymousExecutorAddress);
  console.log("Owner:", deployer.address);
  console.log("Network:", network.name);
  console.log("═".repeat(60));
  
  // Generate ABI checksums
  const abiChecksums = generateABIChecksums();
  
  // Save deployment info
  const deploymentInfo = {
    network: network.name,
    chainId: network.chainId.toString(),
    contracts: deployedContracts,
    deployer: deployer.address,
    timestamp: new Date().toISOString(),
    parameters: {
      maxSlippageBps,
      minDeadlineOffset,
      bridgeFeeBps,
      protocolFeeBps,
      performanceFeeBps,
      managementFeeBps,
      revealDelay,
      relayerFeeBps,
    },
    approvedRouters: routers,
    approvedTokens: tokens,
    abiChecksums,
  };
  
  const deploymentsDir = "./deployments";
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir);
  }
  
  const deploymentFile = `${deploymentsDir}/${network.name}-${Date.now()}.json`;
  fs.writeFileSync(deploymentFile, JSON.stringify(deploymentInfo, null, 2));
  console.log("\nDeployment info saved to:", deploymentFile);
  
  // Save latest deployment for easy reference
  const latestFile = `${deploymentsDir}/${network.name}-latest.json`;
  fs.writeFileSync(latestFile, JSON.stringify(deploymentInfo, null, 2));
  console.log("Latest deployment saved to:", latestFile);
  
  // Export ABIs
  console.log("\nExporting ABIs...");
  exportABIs();
  console.log("✓ ABIs exported to ./deployments/abis/");
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
      "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
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

// Helper: Get USDC address for network
function getUSDCForNetwork(chainId) {
  const usdc = {
    1: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    42161: "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
    137: "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    56: "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    8453: "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
  };
  return usdc[Number(chainId)];
}

// Helper: Generate ABI checksums for validation
function generateABIChecksums() {
  const contracts = [
    "VELTradeExecutor",
    "VELMultiDEXRouter",
    "VELPooledTradingVault",
    "VELCrosschainBridge",
    "VELAtomicSwapHTLC",
    "VELAnonymousOrderExecutor",
  ];
  
  const checksums = {};
  
  for (const contract of contracts) {
    try {
      const artifactPath = `./artifacts/${contract}.sol/${contract}.json`;
      if (fs.existsSync(artifactPath)) {
        const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
        const abiString = JSON.stringify(artifact.abi);
        checksums[contract] = crypto.createHash("sha256").update(abiString).digest("hex");
      }
    } catch (error) {
      console.log(`⚠ Could not generate checksum for ${contract}`);
    }
  }
  
  return checksums;
}

// Helper: Export ABIs to separate files
function exportABIs() {
  const contracts = [
    "VELTradeExecutor",
    "VELMultiDEXRouter",
    "VELPooledTradingVault",
    "VELCrosschainBridge",
    "VELAtomicSwapHTLC",
    "VELAnonymousOrderExecutor",
  ];
  
  const abiDir = "./deployments/abis";
  if (!fs.existsSync(abiDir)) {
    fs.mkdirSync(abiDir, { recursive: true });
  }
  
  for (const contract of contracts) {
    try {
      const artifactPath = `./artifacts/${contract}.sol/${contract}.json`;
      if (fs.existsSync(artifactPath)) {
        const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
        fs.writeFileSync(
          `${abiDir}/${contract}.json`,
          JSON.stringify(artifact.abi, null, 2)
        );
      }
    } catch (error) {
      console.log(`⚠ Could not export ABI for ${contract}`);
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
